#!/usr/bin/env python3
"""Flock Mahnwesen Playbook Runner.

Command-line tool for running dunning processes using Flock.
Supports dry-run mode and tenant-specific processing.
"""

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.mahnwesen import DunningPlaybook
from agents.mahnwesen.playbooks import DunningContext
from agents.mahnwesen.providers import LocalOverdueProvider


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration.

    Args:
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant ID format.

    Args:
        tenant_id: Tenant ID to validate

    Returns:
        Validated tenant ID

    Raises:
        ValueError: If tenant ID format is invalid
    """
    import re

    # UUID format validation (relaxed - accepts any UUID version)
    pattern = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

    if not re.match(pattern, tenant_id):
        raise ValueError(f"Invalid tenant ID format: {tenant_id}")

    return tenant_id


def create_context(
    tenant_id: str,
    dry_run: bool = False,
    limit: int = 100,
    correlation_id: str | None = None,
    requester: str | None = None,
) -> DunningContext:
    """Create dunning context.

    Args:
        tenant_id: Tenant ID
        dry_run: Enable dry-run mode
        limit: Maximum number of invoices to process
        correlation_id: Optional correlation ID

    Returns:
        Dunning context
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    if requester is None:
        requester = os.getenv("MVR_REQUESTER") or os.getenv("USER", "operate-cli")

    return DunningContext(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        dry_run=dry_run,
        limit=limit,
        requester=requester,
        overdue_provider=LocalOverdueProvider(),
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Flock Mahnwesen Playbook Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run for tenant
  python tools/flock/playbook_mahnwesen.py --tenant 00000000-0000-0000-0000-000000000001 --dry-run
  
  # Process with limit
  python tools/flock/playbook_mahnwesen.py --tenant 00000000-0000-0000-0000-000000000001 --limit 25
  
  # Verbose output
  python tools/flock/playbook_mahnwesen.py --tenant 00000000-0000-0000-0000-000000000001 --verbose
        """,
    )

    parser.add_argument(
        "--tenant", help="Tenant ID (UUID format) - required except for --report-daily"
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Enable dry-run mode (no actual processing)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of invoices to process (default: 100)",
    )

    parser.add_argument(
        "--correlation-id", help="Correlation ID for tracing (default: auto-generated)"
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    parser.add_argument("--config-override", help="Override configuration (JSON format)")

    parser.add_argument(
        "--report-path",
        help="Path to save JSON report (default: artifacts/reports/mahnwesen/<tenant>/dry_run_YYYYMMDD.json)",
    )

    parser.add_argument("--today", help="Override today's date (ISO format: YYYY-MM-DD)")

    parser.add_argument(
        "--validate-templates",
        action="store_true",
        help="Validate templates exist and are loadable",
    )

    parser.add_argument(
        "--preview", action="store_true", help="Preview notices without sending (MVR mode)"
    )

    parser.add_argument(
        "--approve", metavar="NOTICE_ID", help="Approve notice for sending (requires --comment)"
    )

    parser.add_argument("--reject", metavar="NOTICE_ID", help="Reject notice (requires --comment)")

    parser.add_argument("--comment", help="Required comment for approve/reject actions")

    parser.add_argument(
        "--actor",
        help="Actor performing approve/reject (defaults to current $USER)",
    )

    parser.add_argument(
        "--rate-limit", type=int, help="Rate limit: max events per run (overrides config)"
    )

    parser.add_argument(
        "--kill-switch",
        action="store_true",
        help="Enable kill switch: prevent all sending (0 events)",
    )

    parser.add_argument(
        "--live", action="store_true", help="Live mode: actually send emails via Brevo"
    )

    parser.add_argument(
        "--report-daily", action="store_true", help="Generate daily KPI report for all tenants"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Handle daily report command (no tenant required)
        if args.report_daily:
            return handle_daily_report(args, logger)

        # Validate tenant ID (required for other commands)
        if not args.tenant and not hasattr(args, "_tenant_not_required"):
            logger.error("--tenant is required (except for --report-daily)")
            sys.exit(1)

        # Handle commands that don't require tenant
        if not args.tenant:
            return  # Already handled by daily report

        tenant_id = validate_tenant_id(args.tenant)
        logger.info(f"Processing tenant: {tenant_id}")

        # Handle template validation
        if args.validate_templates:
            return handle_template_validation(tenant_id, args, logger)

        # Handle MVR preview mode
        if args.preview:
            return handle_mvr_preview(tenant_id, args, logger)

        # Handle approve/reject
        if args.approve or args.reject:
            return handle_approve_reject(tenant_id, args, logger)

        # Check kill switch
        if args.kill_switch:
            logger.warning("Kill switch enabled - no events will be dispatched")
            print("⚠️  KILL SWITCH ACTIVE: No events will be sent")
            import json as json_module

            print(
                json_module.dumps(
                    {
                        "success": True,
                        "kill_switch": True,
                        "events_dispatched": 0,
                        "message": "Kill switch prevented all sending",
                    },
                    indent=2,
                )
            )
            sys.exit(0)

        # Create context
        context = create_context(
            tenant_id=tenant_id,
            dry_run=args.dry_run if not args.live else False,
            limit=args.limit,
            correlation_id=args.correlation_id,
            requester=f"{os.getenv('USER', 'operate-cli')}:{'live' if args.live else 'dry-run' if args.dry_run else 'run'}",
        )

        # Apply rate limit override
        if args.rate_limit:
            context.config.max_notices_per_hour = args.rate_limit
            logger.info(f"Rate limit override: {args.rate_limit} notices per run")

        # Apply config overrides if provided
        if args.config_override:
            import json

            overrides = json.loads(args.config_override)
            for key, value in overrides.items():
                setattr(context.config, key, value)

        # Create playbook
        playbook = DunningPlaybook(context.config)

        # Run dunning process
        logger.info(
            "Starting dunning process",
            extra={
                "tenant_id": tenant_id,
                "dry_run": args.dry_run,
                "limit": args.limit,
                "correlation_id": context.correlation_id,
            },
        )

        result = playbook.run_once(context)

        # Generate report
        report_data = generate_report(result, context, args.today)

        # Save report if requested
        if args.report_path or args.dry_run:
            report_path = save_report(report_data, args.report_path, tenant_id, args.today)
            logger.info(f"Report saved to: {report_path}")

        # Output results
        if result.success:
            # Print summary
            print_summary(report_data)

            logger.info(
                "Dunning process completed successfully",
                extra={
                    "notices_created": result.notices_created,
                    "events_dispatched": result.events_dispatched,
                    "processing_time": result.processing_time_seconds,
                    "warnings": result.warnings,
                },
            )

            # Exit with success
            sys.exit(0)
        else:
            logger.error(
                "Dunning process failed",
                extra={"errors": result.errors, "warnings": result.warnings},
            )

            # Exit with error
            sys.exit(1)

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


def generate_report(result, context, today_override: str | None = None) -> dict:
    """Generate report data.

    Args:
        result: Dunning process result
        context: Dunning context
        today_override: Override today's date

    Returns:
        Report data dictionary
    """
    today = datetime.now(UTC)
    if today_override:
        try:
            today = datetime.fromisoformat(today_override).replace(tzinfo=UTC)
        except ValueError:
            pass  # Use current date if override is invalid

    return {
        "tenant_id": context.tenant_id,
        "correlation_id": context.correlation_id,
        "dry_run": context.dry_run,
        "generated_at": datetime.now(UTC).isoformat(),
        "report_date": today.date().isoformat(),
        "summary": {
            "total_overdue": getattr(result, "total_overdue", 0),
            "stage_1_count": getattr(result, "stage_1_count", 0),
            "stage_2_count": getattr(result, "stage_2_count", 0),
            "stage_3_count": getattr(result, "stage_3_count", 0),
            "notices_created": getattr(result, "notices_created", 0),
            "events_dispatched": getattr(result, "events_dispatched", 0),
            "processing_time_seconds": getattr(result, "processing_time_seconds", 0.0),
        },
        "status": "success" if result.success else "failed",
        "errors": getattr(result, "errors", []),
        "warnings": getattr(result, "warnings", []),
    }


def save_report(
    report_data: dict, report_path: str | None, tenant_id: str, today_override: str | None = None
) -> str:
    """Save report to file.

    Args:
        report_data: Report data to save
        report_path: Custom report path
        tenant_id: Tenant ID
        today_override: Override today's date

    Returns:
        Path to saved report
    """
    if report_path:
        path = Path(report_path)
    else:
        # Default path: artifacts/reports/mahnwesen/<tenant>/dry_run_YYYYMMDD.json
        today = datetime.now(UTC)
        if today_override:
            try:
                today = datetime.fromisoformat(today_override).replace(tzinfo=UTC)
            except ValueError:
                pass

        report_dir = Path("artifacts/reports/mahnwesen") / tenant_id
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"dry_run_{today.strftime('%Y%m%d')}.json"

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Save report
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    return str(path)


def print_summary(report_data: dict) -> None:
    """Print summary to console.

    Args:
        report_data: Report data
    """
    summary = report_data["summary"]

    print("\n" + "=" * 60)
    print("MAHNWESEN DRY-RUN SUMMARY")
    print("=" * 60)
    print(f"Tenant: {report_data['tenant_id']}")
    print(f"Date: {report_data['report_date']}")
    print(f"Status: {report_data['status'].upper()}")
    print("-" * 60)
    print(f"Total Overdue: {summary['total_overdue']}")
    print(f"Stage 1: {summary['stage_1_count']}")
    print(f"Stage 2: {summary['stage_2_count']}")
    print(f"Stage 3: {summary['stage_3_count']}")
    print(f"Notices Created: {summary['notices_created']}")
    print(f"Events Dispatched: {summary['events_dispatched']}")
    print(f"Processing Time: {summary['processing_time_seconds']:.2f}s")

    if report_data.get("warnings"):
        print(f"\nWarnings: {len(report_data['warnings'])}")
        for warning in report_data["warnings"]:
            print(f"  - {warning}")

    if report_data.get("errors"):
        print(f"\nErrors: {len(report_data['errors'])}")
        for error in report_data["errors"]:
            print(f"  - {error}")

    print("=" * 60)


def handle_template_validation(tenant_id: str, args, logger) -> None:
    """Validate templates exist and are loadable.

    Args:
        tenant_id: Tenant ID
        args: Command line arguments
        logger: Logger instance
    """
    from agents.mahnwesen.config import DunningConfig
    from agents.mahnwesen.dto import DunningStage
    from agents.mahnwesen.playbooks import TemplateEngine

    logger.info(f"Validating templates for tenant {tenant_id}")

    try:
        config = DunningConfig.from_tenant(tenant_id)
        template_engine = TemplateEngine(config)

        # Try to load all stage templates
        stages = [DunningStage.STAGE_1, DunningStage.STAGE_2, DunningStage.STAGE_3]
        results = []

        for stage in stages:
            template_name = f"stage_{stage.value}.jinja.txt"
            try:
                template = template_engine.env.get_template(template_name)
                results.append(
                    {
                        "stage": stage.value,
                        "template": template_name,
                        "path": template.filename,
                        "status": "OK",
                    }
                )
                logger.info(f"✓ Template {template_name} found at {template.filename}")
            except Exception as e:
                results.append(
                    {
                        "stage": stage.value,
                        "template": template_name,
                        "status": "ERROR",
                        "error": str(e),
                    }
                )
                logger.error(f"✗ Template {template_name} not found: {e}")

        # Print summary
        print("\n" + "=" * 60)
        print("TEMPLATE VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Tenant: {tenant_id}")
        print("-" * 60)
        for result in results:
            status_symbol = "✓" if result["status"] == "OK" else "✗"
            print(f"{status_symbol} Stage {result['stage']}: {result['status']}")
            if result["status"] == "OK":
                print(f"  Path: {result['path']}")
            else:
                print(f"  Error: {result.get('error', 'Unknown')}")
        print("=" * 60)

        # Exit with appropriate code
        all_ok = all(r["status"] == "OK" for r in results)
        if all_ok:
            logger.info("All templates validated successfully")
            sys.exit(0)
        else:
            logger.error("Template validation failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Template validation failed: {e}")
        sys.exit(1)


def handle_mvr_preview(tenant_id: str, args, logger) -> None:
    """Handle MVR preview mode - show notices without sending."""

    from agents.mahnwesen import DunningPlaybook

    logger.info(f"MVR Preview mode for tenant {tenant_id}")

    try:
        context = create_context(
            tenant_id=tenant_id,
            dry_run=True,
            limit=args.limit,
            correlation_id=args.correlation_id,
            requester=f"{os.getenv('USER', 'operate-cli')}:preview",
        )

        playbook = DunningPlaybook(context.config)
        result = playbook.run_once(context)

        print("\n" + "=" * 60)
        print("MVR PREVIEW - NOTICES READY FOR REVIEW")
        print("=" * 60)
        print(f"Tenant: {tenant_id}")
        print(f"Total Overdue: {result.total_overdue}")
        print(f"Stage 1: {result.stage_1_count}")
        print(f"Stage 2: {result.stage_2_count}")
        print(f"Stage 3: {result.stage_3_count}")
        print(f"Notices Created: {result.notices_created}")
        print("=" * 60)

        metadata = result.metadata or {}
        blocked = metadata.get("blocked_without_approval", [])
        approval_records = metadata.get("approval_records", [])
        prepared = metadata.get("dry_run_prepared", [])

        if blocked:
            print("\nBlocked Notices (Approval required):")
            for entry in blocked:
                print(
                    f"  - {entry['notice_id']} | stage {entry['stage']} | key {entry['idempotency_key'][:8]}… | reason: {entry.get('reason', 'pending')}"
                )

        pending = [rec for rec in approval_records if rec.get("status") == "pending"]
        if pending:
            print("\nPending Approvals:")
            for entry in pending:
                print(
                    f"  - {entry['notice_id']} (stage {entry['stage']}) awaiting approval"
                )

        if prepared:
            print("\nDry-Run Prepared Notices:")
            for entry in prepared:
                print(
                    f"  - {entry['notice_id']} | stage {entry['stage']} | key {entry['idempotency_key'][:8]}…"
                )

        print("\nTo approve notices for sending:")
        print(f"  python {sys.argv[0]} --tenant {tenant_id} --approve NOTICE-ID --comment 'Reason'")
        print("\nTo reject notices:")
        print(f"  python {sys.argv[0]} --tenant {tenant_id} --reject NOTICE-ID --comment 'Reason'")
        print("=" * 60)

        sys.exit(0 if result.success else 1)

    except Exception as e:
        logger.error(f"MVR preview failed: {e}")
        sys.exit(1)


def handle_approve_reject(tenant_id: str, args, logger) -> None:
    """Handle approve/reject actions with audit trail.

    Args:
        tenant_id: Tenant ID
        args: Command line arguments
        logger: Logger instance
    """
    from agents.mahnwesen.approval_store import ApprovalStore

    if not args.comment:
        logger.error("--comment is required for approve/reject actions")
        print("ERROR: --comment is required for approve/reject actions")
        sys.exit(1)

    action = "approve" if args.approve else "reject"
    notice_id = args.approve or args.reject

    actor = args.actor or os.getenv("MVR_ACTOR") or os.getenv("USER", "unknown")
    correlation_id = args.correlation_id or str(uuid.uuid4())

    store = ApprovalStore()
    record = store.get_by_notice(tenant_id, notice_id)

    if record is None:
        logger.error(
            "Approval record not found",
            extra={"tenant_id": tenant_id, "notice_id": notice_id},
        )
        print(f"ERROR: No approval entry found for notice {notice_id}.")
        sys.exit(1)

    if actor == record.requester:
        logger.error(
            "4-Augen-Prinzip verletzt",
            extra={
                "tenant_id": tenant_id,
                "notice_id": notice_id,
                "stage": record.stage.value,
                "requester": record.requester,
                "actor": actor,
            },
        )
        print("ERROR: Approver darf nicht identisch mit dem Requester sein (4-Augen-Prinzip).")
        sys.exit(1)

    logger.info(
        f"MVR {action}: {notice_id} for tenant {tenant_id}",
        extra={
            "actor": actor,
            "notice_id": notice_id,
            "stage": record.stage.value,
            "idempotency_key": record.idempotency_key,
        },
    )

    try:
        if action == "approve":
            updated = store.approve(
                tenant_id=tenant_id,
                notice_id=notice_id,
                stage=record.stage,
                approver=actor,
                comment=args.comment,
                actor=actor,
                correlation_id=correlation_id,
            )
        else:
            updated = store.reject(
                tenant_id=tenant_id,
                notice_id=notice_id,
                stage=record.stage,
                approver=actor,
                comment=args.comment,
                actor=actor,
                correlation_id=correlation_id,
            )

        audit_entry = {
            "tenant_id": tenant_id,
            "notice_id": notice_id,
            "stage": updated.stage.value,
            "action": action,
            "comment": args.comment,
            "actor": actor,
            "requester": record.requester,
            "status": updated.status,
            "idempotency_key": updated.idempotency_key,
            "timestamp": datetime.now(UTC).isoformat(),
            "correlation_id": correlation_id,
        }

        audit_dir = Path("artifacts/reports/mahnwesen") / tenant_id / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = (
            audit_dir / f"{notice_id}_{action}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump(audit_entry, f, indent=2, ensure_ascii=False)

        logger.info(f"Audit entry saved: {audit_file}")

        print("\n" + "=" * 60)
        print(f"MVR {action.upper()} - AUDIT TRAIL")
        print("=" * 60)
        print(f"Notice ID: {notice_id}")
        print(f"Stage: S{updated.stage.value}")
        print(f"Action: {action}")
        print(f"Comment: {args.comment}")
        print(f"Actor: {actor}")
        print(f"Requester: {record.requester}")
        print(f"Idempotency Key: {updated.idempotency_key}")
        print(f"Timestamp: {audit_entry['timestamp']}")
        print(f"Audit File: {audit_file}")
        print("=" * 60)

        if action == "approve":
            print("\n✓ Notice approved for sending")
            print("  Next: Run with --live to actually send")
        else:
            print("\n✓ Notice rejected")
            print("  Notice will not be sent")

        sys.exit(0)

    except Exception as e:
        logger.error(f"Approve/reject failed: {e}")
        sys.exit(1)


def handle_daily_report(args, logger) -> None:
    """Generate daily KPI report for all tenants.

    Args:
        args: Command line arguments
        logger: Logger instance
    """
    logger.info("Generating daily KPI report for all tenants")

    try:
        # Get list of tenants (for now, use default test tenant)
        # In production, this would query the database for active tenants
        tenants = ["00000000-0000-0000-0000-000000000001"]

        today = datetime.now(UTC)
        if args.today:
            try:
                today = datetime.fromisoformat(args.today).replace(tzinfo=UTC)
            except ValueError:
                logger.warning(f"Invalid --today format: {args.today}, using current date")

        all_reports = []

        for tenant_id in tenants:
            try:
                report = generate_tenant_daily_kpis(tenant_id, today, logger)
                all_reports.append(report)

                # Save JSON report
                report_dir = Path("artifacts/reports/mahnwesen") / tenant_id
                report_dir.mkdir(parents=True, exist_ok=True)

                json_file = report_dir / f"{today.strftime('%Y-%m-%d')}.json"
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)

                # Save Markdown report
                md_file = report_dir / f"{today.strftime('%Y-%m-%d')}.md"
                with open(md_file, "w", encoding="utf-8") as f:
                    f.write(format_report_as_markdown(report))

                logger.info(f"Reports saved for {tenant_id}: {json_file}, {md_file}")

            except Exception as e:
                logger.error(f"Failed to generate report for tenant {tenant_id}: {e}")
                all_reports.append({"tenant_id": tenant_id, "error": str(e), "status": "failed"})

        # Print summary
        print("\n" + "=" * 60)
        print("DAILY KPI REPORT SUMMARY")
        print("=" * 60)
        print(f"Report Date: {today.date().isoformat()}")
        print(f"Tenants Processed: {len(all_reports)}")
        print("-" * 60)
        for report in all_reports:
            if report.get("error"):
                print(f"✗ {report['tenant_id']}: ERROR - {report['error']}")
            else:
                kpis = report.get("kpis", {})
                print(
                    f"✓ {report['tenant_id']}: {kpis.get('total_overdue', 0)} overdue, {kpis.get('total_sent', 0)} sent"
                )
        print("=" * 60)

        sys.exit(0)

    except Exception as e:
        logger.error(f"Daily report generation failed: {e}")
        sys.exit(1)


def generate_tenant_daily_kpis(tenant_id: str, report_date: datetime, logger) -> dict:
    """Generate daily KPIs for a specific tenant.

    Args:
        tenant_id: Tenant ID
        report_date: Date for the report
        logger: Logger instance

    Returns:
        Dictionary with KPI data
    """
    from agents.mahnwesen.config import DunningConfig
    from agents.mahnwesen.playbooks import DunningContext, DunningPlaybook

    config = DunningConfig.from_tenant(tenant_id)
    context = DunningContext(
        tenant_id=tenant_id,
        correlation_id=f"daily-kpi-{report_date.strftime('%Y%m%d')}",
        dry_run=True,  # KPI generation is read-only
        limit=1000,
    )

    playbook = DunningPlaybook(config)
    result = playbook.run_once(context)

    # Calculate cycle_time_median (creation → sent/rejected)
    # Zeitbasis: Europe/Berlin (CET/CEST)
    # In production würde dies aus Audit-Trail/DB berechnet
    cycle_times = []  # In production: real times from DB
    cycle_time_median = _calculate_median(cycle_times) if cycle_times else None

    return {
        "tenant_id": tenant_id,
        "report_date": report_date.date().isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "timezone": "Europe/Berlin",  # For cycle time calculations
        "status": "success" if result.success else "failed",
        "kpis": {
            "total_overdue": result.total_overdue,
            "stage_1_count": result.stage_1_count,
            "stage_2_count": result.stage_2_count,
            "stage_3_count": result.stage_3_count,
            "notices_ready": result.notices_created,
            "total_sent": 0,  # Would be tracked in production
            "bounced": 0,  # Would be tracked in production
            "errors": len(result.errors) if result.errors else 0,
            "escalations": result.stage_3_count,  # Stage 3 is escalation
            "cycle_time_median_hours": cycle_time_median,  # Median Durchlaufzeit (Stunden)
        },
        "errors": result.errors or [],
        "warnings": result.warnings or [],
    }


def _calculate_median(values: list[float]) -> float | None:
    """Calculate median of a list of values.

    Args:
        values: List of numeric values

    Returns:
        Median value or None if empty
    """
    if not values:
        return None

    sorted_values = sorted(values)
    n = len(sorted_values)

    if n % 2 == 0:
        # Even number: average of two middle values
        return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
    else:
        # Odd number: middle value
        return sorted_values[n // 2]


def format_report_as_markdown(report: dict) -> str:
    """Format report data as Markdown.

    Args:
        report: Report data dictionary

    Returns:
        Formatted Markdown string
    """
    kpis = report.get("kpis", {})

    md = f"""# Mahnwesen Daily KPI Report

**Tenant:** `{report['tenant_id']}`  
**Report Date:** {report['report_date']}  
**Generated:** {report['generated_at']}  
**Status:** {report['status']}

## Key Performance Indicators

| Metric | Count |
|--------|-------|
| Total Overdue | {kpis.get('total_overdue', 0)} |
| Stage 1 | {kpis.get('stage_1_count', 0)} |
| Stage 2 | {kpis.get('stage_2_count', 0)} |
| Stage 3 | {kpis.get('stage_3_count', 0)} |
| Notices Ready | {kpis.get('notices_ready', 0)} |
| Total Sent | {kpis.get('total_sent', 0)} |
| Bounced | {kpis.get('bounced', 0)} |
| Errors | {kpis.get('errors', 0)} |
| Escalations | {kpis.get('escalations', 0)} |
| Cycle Time (Median) | {kpis.get('cycle_time_median_hours', 'N/A')} hours |

## Summary

- **Total Invoices Overdue:** {kpis.get('total_overdue', 0)}
- **Notices Ready for Send:** {kpis.get('notices_ready', 0)}
- **Escalations (Stage 3):** {kpis.get('escalations', 0)}
- **Cycle Time (Median):** {kpis.get('cycle_time_median_hours', 'N/A')} hours (Europe/Berlin)

**Note:** Cycle time measures the duration from notice creation to final action (sent/rejected).
Timezone basis is Europe/Berlin (CET/CEST) for all timestamps.

"""

    if report.get("errors"):
        md += "\n## Errors\n\n"
        for error in report["errors"]:
            md += f"- {error}\n"

    if report.get("warnings"):
        md += "\n## Warnings\n\n"
        for warning in report["warnings"]:
            md += f"- {warning}\n"

    md += "\n---\n*Generated by 0Admin Mahnwesen Agent*\n"

    return md


if __name__ == "__main__":
    main()
