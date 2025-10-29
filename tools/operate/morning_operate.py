"""Morning Operate orchestrator.

Runs KPI aggregation, canary decision, rollout step and bounce reconcile
for one or multiple tenants and produces a consolidated summary.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from tools.operate.bounce_reconcile import BounceReconciler
from tools.operate.canary_engine import (
    ARTIFACT_ROOT,
    determine_next_action,
    load_blocklist_stats,
    load_operate_state as load_canary_state,
    load_thresholds,
    Thresholds,
    write_decision,
)
from tools.operate.canary_rollout import apply_rollout, determine_target_percentage
from tools.operate.kpi_engine import KpiAggregator, KpiReport, LocalArtifactDataSource, discover_tenants, write_reports

TZ_EUROPE_BERLIN = ZoneInfo("Europe/Berlin")


def _tenant_input_list(all_tenants: bool, tenant: str | None) -> list[str]:
    if all_tenants:
        tenants = discover_tenants()
        if not tenants:
            env_tenant = os.getenv("TENANT_DEFAULT")
            return [env_tenant] if env_tenant else []
        return tenants
    if tenant:
        return [tenant]
    env_tenant = os.getenv("TENANT_DEFAULT")
    return [env_tenant] if env_tenant else []


def _kpi_to_dict(report: KpiReport) -> dict[str, Any]:
    metrics = report.metrics
    return {
        "metrics": {
            "notices_created": metrics.notices_created,
            "notices_sent": metrics.notices_sent,
            "errors": metrics.errors,
            "hard_bounces": metrics.hard_bounces,
            "soft_bounces": metrics.soft_bounces,
            "retry_depth": metrics.retry_depth,
            "dlq_depth": metrics.dlq_depth,
            "cycle_time_median_hours": metrics.cycle_time_median_hours,
        }
    }


def _format_threshold_overrides(thresholds: Thresholds) -> list[str]:
    defaults = Thresholds()
    overrides: list[str] = []
    for field in ("error_rate", "hard_bounce_rate", "dlq_depth", "retry_depth", "min_notices"):
        if getattr(thresholds, field) != getattr(defaults, field):
            overrides.append(f"{field}={getattr(thresholds, field)}")
    return overrides


def _render_summary(
    tenant_id: str,
    report_date: date,
    dry_run: bool,
    report: KpiReport,
    decision: dict[str, Any],
    rollout_info: dict[str, Any],
    bounce_info: dict[str, Any],
    overrides: list[str],
    summary_path: Path,
) -> None:
    metrics = report.metrics
    lines = [
        f"# Morning Operate — Tenant `{tenant_id}`",
        "",
        f"*Date (Europe/Berlin):* {report_date.isoformat()}",
        f"*Generated at:* {datetime.now(UTC).isoformat()}",
        f"*Mode:* {'DRY-RUN' if dry_run else 'LIVE'}",
        "",
        "## KPI Snapshot",
        "",
        f"- Notices Sent: {metrics.notices_sent}",
        f"- Notices Created: {metrics.notices_created}",
        f"- Errors: {metrics.errors}",
        f"- Error Rate: {metrics.errors / max(1, metrics.notices_sent):.4f}",
        f"- Hard Bounces: {metrics.hard_bounces}",
        f"- Hard Bounce Rate: {metrics.hard_bounces / max(1, metrics.notices_sent):.4f}",
        f"- Retry Depth: {metrics.retry_depth}",
        f"- DLQ Depth: {metrics.dlq_depth}",
        f"- Cycle Time Median (h): {metrics.cycle_time_median_hours}",
        "",
    ]

    thresholds = decision.get("thresholds", {})
    lines.append("## Canary Decision")
    lines.append("")
    lines.append(f"- Recommended Action: **{decision['recommended_action']}**")
    for reason in decision.get("reasons", []):
        lines.append(f"  - {reason}")
    lines.append("")
    lines.append("### Thresholds")
    lines.append("")
    for key, value in thresholds.items():
        lines.append(f"- {key}: {value}")
    overrides_text = ", ".join(overrides) if overrides else "None"
    lines.append("")
    lines.append(f"**Overrides active:** {overrides_text}")
    lines.append("")

    lines.append("## Rollout Result")
    lines.append("")
    after = rollout_info.get("after", {})
    before = rollout_info.get("before", {})
    lines.append(f"- Before: {before.get('rollout_percentage', after.get('rollout_percentage'))}% (Kill-Switch: {before.get('kill_switch', after.get('kill_switch'))})")
    lines.append(f"- After: {after.get('rollout_percentage')}% (Kill-Switch: {after.get('kill_switch')})")
    lines.append(f"- Changed: {rollout_info.get('changed')} {'(dry-run preview)' if dry_run else ''}")
    if rollout_info.get("log_path"):
        lines.append(f"- Rollout Log: `{rollout_info['log_path']}`")
    lines.append("")

    lines.append("## Bounce Reconcile")
    lines.append("")
    if hasattr(bounce_info, "processed"):
        processed = bounce_info.processed
        actions_list = bounce_info.actions
        log_path = getattr(bounce_info, "log_path", None)
    else:
        processed = bounce_info.get("processed", [])
        actions_list = bounce_info.get("actions", [])
        log_path = bounce_info.get("log_path")

    lines.append(f"- Events processed: {len(processed)}")
    counter = Counter(action.get("action") for action in actions_list)
    if counter:
        lines.append("- Actions:")
        for action, count in counter.items():
            lines.append(f"  - {action}: {count}")
    if log_path:
        lines.append(f"- Reconcile Log: `{log_path}`")
    lines.append("")

    warnings: list[str] = []
    if metrics.notices_sent < thresholds.get("min_notices", Thresholds.min_notices):
        warnings.append("LOW SAMPLE — HOLD recommended unless manually overridden")
    if overrides:
        warnings.append("Threshold overrides active; review before stepping further")
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for warn in warnings:
            lines.append(f"- {warn}")
        lines.append("")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_morning_for_tenant(
    tenant_id: str,
    report_date: date,
    dry_run: bool,
    base_path: Path = ARTIFACT_ROOT,
) -> dict[str, Any]:
    now_utc = datetime.now(UTC)
    aggregator = KpiAggregator(LocalArtifactDataSource(base_path))
    report = aggregator.build_report(tenant_id, report_date, now=now_utc)

    kpi_json_path = base_path / tenant_id / f"{report_date.isoformat()}.json"
    kpi_md_path = base_path / tenant_id / f"{report_date.isoformat()}.md"
    if not dry_run:
        write_reports(report, base_path=base_path, dry_run=False)

    kpi_dict = _kpi_to_dict(report)
    blocklist_stats = load_blocklist_stats(tenant_id, base_path=base_path)
    state = load_canary_state(tenant_id, base_path=base_path)
    thresholds = load_thresholds(tenant_id)
    decision = determine_next_action(
        tenant_id,
        report_date,
        kpi_dict,
        blocklist_stats,
        state,
        thresholds,
    )

    decision_json_path = None
    decision_md_path = None
    if not dry_run:
        decision_json_path, decision_md_path = write_decision(
            tenant_id, decision, report_date, now_utc, base_path=base_path
        )

    overrides = _format_threshold_overrides(thresholds)

    rollout_info: dict[str, Any] = {}
    if dry_run:
        before = {
            "kill_switch": state.get("kill_switch", False),
            "rollout_percentage": state.get("rollout_percentage", 10),
        }
        after = before.copy()
        action = decision["recommended_action"]
        if action == "BACKOUT":
            after = {"kill_switch": True, "rollout_percentage": min(before["rollout_percentage"], 10)}
        elif action.startswith("GO_"):
            target = determine_target_percentage(before["rollout_percentage"], action)
            after = {"kill_switch": False, "rollout_percentage": target}
        rollout_info = {
            "before": before,
            "after": after,
            "changed": False,
        }
    else:
        rollout_info = apply_rollout(
            tenant_id,
            decision,
            trace_id=f"morning-run-{now_utc.strftime('%H%M%S')}",
            base_path=base_path,
        )

    reconciler = BounceReconciler(tenant_id, base_path=base_path)
    bounce_result = reconciler.process(dry_run=dry_run)

    summary_path = base_path / tenant_id / f"{report_date.isoformat()}_morning_summary.md"
    rollout_info.setdefault("before", {
        "kill_switch": state.get("kill_switch", False),
        "rollout_percentage": state.get("rollout_percentage", 10),
    })
    rollout_info.setdefault("after", rollout_info["before"])
    _render_summary(
        tenant_id,
        report_date,
        dry_run,
        report,
        decision,
        rollout_info,
        bounce_result,
        overrides,
        summary_path,
    )

    bounce_log_obj = (
        getattr(bounce_result, "log_path", None)
        if hasattr(bounce_result, "log_path")
        else bounce_result.get("log_path")
    )
    bounce_log = str(bounce_log_obj) if bounce_log_obj else None
    rollout_log_obj = rollout_info.get("log_path")
    rollout_log = str(rollout_log_obj) if rollout_log_obj else None

    return {
        "tenant_id": tenant_id,
        "date": report_date.isoformat(),
        "dry_run": dry_run,
        "kpi_json": str(kpi_json_path),
        "decision_json": str(decision_json_path) if decision_json_path else None,
        "rollout_log": rollout_log,
        "bounce_log": bounce_log,
        "summary_md": str(summary_path),
        "decision": decision["recommended_action"],
        "rollout_changed": rollout_info.get("changed"),
        "overrides": overrides,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Morning Operate orchestrator")
    parser.add_argument("--tenant", help="Tenant UUID")
    parser.add_argument("--all-tenants", action="store_true", help="Process all tenants with artefacts")
    parser.add_argument("--date", help="Report date (YYYY-MM-DD), defaults to today Europe/Berlin")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist KPI/Decision/Rollout changes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report_date = date.fromisoformat(args.date) if args.date else datetime.now(TZ_EUROPE_BERLIN).date()

    tenants = _tenant_input_list(args.all_tenants, args.tenant)
    if not tenants:
        raise SystemExit("No tenant specified and TENANT_DEFAULT unset")

    results = []
    for tenant_id in tenants:
        result = run_morning_for_tenant(tenant_id, report_date, args.dry_run)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False))
    print("Morning Operate completed" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

