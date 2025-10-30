"""E-Invoice Morning Operate orchestrator.

Runs Generate (with limit), KPI aggregation, optional Approve subset, and Summary-MD
for one or multiple tenants. Produces deterministic reports with PII-redaction.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from agents.einvoice import (
    NumberingService,
    approve,
    build_facturx_document,
    build_sample_invoice,
    build_sample_profile,
    build_xrechnung_document,
    iter_sample_scenarios,
    validate_facturx,
    validate_xrechnung,
    write_package,
)
from tools.operate.einvoice_kpi import (
    ARTIFACT_ROOT,
    EInvoiceKpiAggregator,
    LocalArtifactDataSource,
    discover_tenants,
    write_reports,
)

TZ_EUROPE_BERLIN = ZoneInfo("Europe/Berlin")
# BASE_DIR sollte Workspace-Root sein, da write_package bereits "artifacts/reports/einvoice" anhängt
BASE_DIR = Path(".")


def _tenant_input_list(all_tenants: bool, tenant: str | None) -> list[str]:
    """Bestimme Tenant-Liste basierend auf Args."""
    if all_tenants:
        tenants = discover_tenants()
        if not tenants:
            env_tenant = os.environ.get("TENANT_DEFAULT")
            return [env_tenant] if env_tenant else []
        return tenants
    if tenant:
        return [tenant]
    env_tenant = os.environ.get("TENANT_DEFAULT")
    return [env_tenant] if env_tenant else []


def _make_now_provider(start: datetime) -> Callable[[], datetime]:
    """Erstelle deterministischen now-Provider."""
    tick = count()

    def _next() -> datetime:
        return start + timedelta(seconds=next(tick))

    return _next


def _generate_invoices(
    tenant_id: str,
    count_limit: int,
    base_dir: Path,
    now_provider: Callable[[], datetime],
    format_name: str = "facturx",
) -> dict[str, Any]:
    """Generiere E-Invoices bis zum Limit."""
    numbering = NumberingService(clock=now_provider)
    profile = build_sample_profile(tenant_id)

    generated = []
    scenarios = list(iter_sample_scenarios())
    actual_count = min(count_limit, len(scenarios))

    for idx, scenario in enumerate(scenarios[:actual_count]):
        invoice_id = f"{tenant_id}-{scenario.code}"
        invoice = build_sample_invoice(
            scenario,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            issue_date=datetime(2025, 1, 1, tzinfo=timezone.utc).date(),
            due_date=datetime(2025, 1, 15, tzinfo=timezone.utc).date(),
            payment_terms=profile.payment_terms,
            now_provider=now_provider,
        )

        reservation_id = numbering.reserve(tenant_id, invoice.issue_date)
        invoice_no = numbering.commit(reservation_id)
        invoice.invoice_no = invoice_no

        document_ts = now_provider()

        if format_name == "facturx":
            pdf_bytes, xml_bytes = build_facturx_document(invoice, profile, document_ts)
            validation = validate_facturx(xml_bytes)
            files = {
                "invoice.pdf": pdf_bytes,
                "invoice.xml": xml_bytes,
                "validation.json": json.dumps(validation.to_dict(), indent=2, sort_keys=True).encode("utf-8"),
            }
        elif format_name == "xrechnung":
            xml_bytes = build_xrechnung_document(invoice, profile, document_ts)
            validation = validate_xrechnung(xml_bytes)
            files = {
                "invoice.xml": xml_bytes,
                "validation.json": json.dumps(validation.to_dict(), indent=2, sort_keys=True).encode("utf-8"),
            }
        else:
            raise ValueError(f"Unsupported format: {format_name}")

        package_dir, manifest_hash = write_package(
            base_dir,
            tenant_id,
            invoice_no,
            files,
            now=now_provider(),
            previous_hash=None,
            generator_version="facturx-pdfa-best-effort-1.0.0",
        )

        generated.append(
            {
                "invoice_no": invoice_no,
                "invoice_id": invoice_id,
                "format": format_name,
                "validation": validation.to_dict(),
                "package_dir": str(package_dir),
            }
        )

    return {"generated": generated, "count": len(generated)}


def _render_summary(
    tenant_id: str,
    report_date: date,
    dry_run: bool,
    generate_info: dict[str, Any],
    kpi_report: Any,
    summary_path: Path,
) -> None:
    """Erstelle Summary-Markdown."""
    lines = [
        f"# E-Invoice Morning Operate — Tenant `{tenant_id}`",
        "",
        f"*Date (Europe/Berlin):* {report_date.isoformat()}",
        f"*Generated at:* {datetime.now(UTC).isoformat()}",
        f"*Mode:* {'DRY-RUN' if dry_run else 'LIVE'}",
        "",
        "## Generation",
        "",
        f"- Invoices Generated: {generate_info.get('count', 0)}",
        "",
        "## KPI Summary",
        "",
    ]

    if kpi_report:
        metrics = kpi_report.metrics
        lines.extend(
            [
                f"- Total: {metrics.count_total}",
                f"- Validation OK: {metrics.count_ok}",
                f"- Schema Failures: {metrics.schema_fail}",
                f"- Schematron Failures: {metrics.schematron_fail}",
                f"- PDF/A Checks OK: {metrics.pdfa_checks_ok} / {metrics.pdfa_checks_total}",
            ]
        )

    lines.append("")

    # Summary immer schreiben (auch im Dry-Run)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_morning_for_tenant(
    tenant_id: str,
    report_date: date,
    dry_run: bool,
    count_limit: int = 10,
    format_name: str = "facturx",
    base_path: Path = BASE_DIR,
) -> dict[str, Any]:
    """Führe Morning-Operate für einen Tenant aus."""
    now_utc = datetime.now(UTC)
    start_timestamp = datetime.combine(report_date, datetime.min.time(), tzinfo=TZ_EUROPE_BERLIN).astimezone(UTC)
    now_provider = _make_now_provider(start_timestamp)

    # 1. Generate (mit Limit)
    generate_info = _generate_invoices(tenant_id, count_limit, base_path, now_provider, format_name=format_name)

    # 2. KPI-Aggregation
    # LocalArtifactDataSource muss denselben base_path verwenden wie write_package
    # write_package schreibt nach: base_dir/artifacts/reports/einvoice/<tenant>/<invoice_no>/
    # LocalArtifactDataSource sucht nach: base_path/artifacts/reports/einvoice/<tenant>/<invoice_no>/
    # Also: base_path für LocalArtifactDataSource sollte base_path / "artifacts" / "reports" / "einvoice" sein
    artifact_base_path = base_path / "artifacts" / "reports" / "einvoice"
    data_source = LocalArtifactDataSource(base_path=artifact_base_path)
    aggregator = EInvoiceKpiAggregator(data_source)
    kpi_report = aggregator.build_report(tenant_id, report_date, now=now_utc)

    if not dry_run:
        write_reports(kpi_report, base_path=artifact_base_path, dry_run=False)

    # 3. Summary-MD (immer schreiben, auch im Dry-Run)
    # Summary wird nach artifact_base_path geschrieben (konsistent mit Reports und Invoices)
    summary_path = artifact_base_path / tenant_id / f"{report_date.isoformat()}_summary.md"
    _render_summary(tenant_id, report_date, dry_run, generate_info, kpi_report, summary_path)

    return {
        "tenant_id": tenant_id,
        "report_date": report_date.isoformat(),
        "generate_info": generate_info,
        "kpi_report": kpi_report.to_dict() if hasattr(kpi_report, "to_dict") else None,
        "summary_path": str(summary_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="E-Invoice Morning Operate")
    parser.add_argument("--tenant", help="Specific tenant UUID")
    parser.add_argument("--all-tenants", action="store_true", help="Process all tenants")
    parser.add_argument("--date", help="Report date (YYYY-MM-DD) in Europe/Berlin timezone")
    parser.add_argument("--dry-run", action="store_true", help="Skip writes, generate summary")
    parser.add_argument("--count", type=int, default=10, help="Max invoices to generate")
    parser.add_argument("--format", choices=["facturx", "xrechnung"], default="facturx", help="Invoice format")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.tenant and args.all_tenants:
        raise SystemExit("--tenant and --all-tenants are mutually exclusive")

    if args.date:
        report_date = date.fromisoformat(args.date)
    else:
        now_local = datetime.now(TZ_EUROPE_BERLIN)
        report_date = now_local.date()

    tenants = _tenant_input_list(args.all_tenants, args.tenant)
    if not tenants:
        raise SystemExit("No tenants specified")

    results = []
    for tenant_id in tenants:
        result = run_morning_for_tenant(
            tenant_id,
            report_date,
            dry_run=args.dry_run,
            count_limit=args.count,
            format_name=args.format,
        )
        results.append(result)

    print(f"Morning Operate completed for {len(results)} tenant(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

