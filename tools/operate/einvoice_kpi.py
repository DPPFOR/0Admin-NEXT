"""Daily KPI aggregation for E-Invoice (07:30 Europe/Berlin).

The module aggregates KPIs from E-Invoice artifacts (validation results,
PDF/A checks, generation counts) and produces JSON/MD reports with PII-redaction.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from tools.operate.notifiers import (
    NotificationPayload,
    emit_stdout,
    maybe_emit_slack,
    write_markdown_summary,
)

TZ_EUROPE_BERLIN = ZoneInfo("Europe/Berlin")
ARTIFACT_ROOT = Path("artifacts/reports/einvoice")


def _redact_pii(text: str) -> str:
    """Redact PII from text (einfache Pattern-basierte Redaction)."""
    # Redact E-Mail-Adressen
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "<EMAIL>", text)
    # Redact IBAN
    text = re.sub(r"\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{1,4}\b", "<IBAN>", text)
    # Redact VAT-IDs
    text = re.sub(r"\b[A-Z]{2}\d{9,}\b", "<VAT_ID>", text)
    return text


@dataclass
class EInvoiceKpiMetrics:
    """KPI metrics for E-Invoice."""

    count_ok: int = 0
    count_total: int = 0
    schema_fail: int = 0
    schematron_fail: int = 0
    pdfa_checks_ok: int = 0
    pdfa_checks_total: int = 0
    duration_ms: float = 0.0
    duration_avg_ms: float = 0.0


@dataclass
class EInvoiceKpiReport:
    """Daily KPI report for E-Invoice."""

    tenant_id: str
    report_date: date
    timezone: str
    generated_at: datetime
    metrics: EInvoiceKpiMetrics
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Konvertiere Report zu JSON-Dict (mit PII-Redaction)."""
        return _report_json(self)


class EInvoiceKpiDataSource(Protocol):
    """Protocol for E-Invoice KPI data sources."""

    def load(self, tenant_id: str, start: datetime, end: datetime) -> dict[str, object]:
        ...


class LocalArtifactDataSource:
    """Default data source using local E-Invoice artifacts."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or ARTIFACT_ROOT

    def load(self, tenant_id: str, start: datetime, end: datetime) -> dict[str, object]:
        """Lade E-Invoice-Artefakte für den gegebenen Zeitraum."""
        tenant_dir = self.base_path / tenant_id
        if not tenant_dir.exists():
            return {"invoices": [], "metadata": {}}

        invoices = []
        metadata: dict[str, object] = {}

        # Suche nach Invoice-Verzeichnissen (direkte Unterverzeichnisse von tenant_dir)
        # write_package schreibt nach: artifacts/reports/einvoice/<tenant>/<invoice_no>/
        for item in tenant_dir.iterdir():
            if not item.is_dir():
                continue
            
            # Prüfe ob validation.json vorhanden ist (direkt im Invoice-Verzeichnis)
            validation_file = item / "validation.json"
            if not validation_file.exists():
                continue

            try:
                validation_data = json.loads(validation_file.read_text(encoding="utf-8"))
                
                # Prüfe created_at Timestamp (falls vorhanden)
                manifest_file = item / "manifest.json"
                created_at: datetime | None = None
                if manifest_file.exists():
                    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    created_str = manifest_data.get("created_at")
                    if created_str:
                        try:
                            created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                        except ValueError:
                            pass

                # Filter nach Zeitraum
                if created_at and (created_at < start or created_at >= end):
                    continue

                invoice_data = {
                    "validation": validation_data,
                    "created_at": created_at.isoformat() if created_at else None,
                }

                # Prüfe PDF/A (falls PDF vorhanden)
                pdf_file = item / "invoice.pdf"
                if pdf_file.exists():
                    pdf_bytes = pdf_file.read_bytes()
                    # Einfache PDF/A-Checks (Best-Effort)
                    pdf_str = pdf_bytes.decode("latin-1", errors="ignore")
                    pdfa_checks = {
                        "has_xmp": "pdfaid:part" in pdf_str or "pdfaid" in pdf_str,
                        "has_af": "factur-x.xml" in pdf_str or "/AF" in pdf_str,
                        "has_embedded": "EmbeddedFile" in pdf_str or "application/xml" in pdf_str,
                    }
                    invoice_data["pdfa_checks"] = pdfa_checks
                else:
                    invoice_data["pdfa_checks"] = None

                invoices.append(invoice_data)

            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                metadata.setdefault("errors", []).append(f"Error reading {validation_file}: {err}")
                continue

        metadata["total_invoices"] = len(invoices)
        metadata["source"] = "LocalArtifactDataSource"

        return {"invoices": invoices, "metadata": metadata}


class EInvoiceKpiAggregator:
    """Aggregate raw data into E-Invoice KPI report."""

    def __init__(self, data_source: EInvoiceKpiDataSource) -> None:
        self.data_source = data_source

    def build_report(
        self,
        tenant_id: str,
        report_date: date,
        now: datetime | None = None,
    ) -> EInvoiceKpiReport:
        """Erstelle KPI-Report für den gegebenen Tag."""
        now = now or datetime.now(UTC)
        start = datetime.combine(report_date, datetime.min.time(), tzinfo=TZ_EUROPE_BERLIN).astimezone(UTC)
        end = start + timedelta(days=1)

        raw = self.data_source.load(tenant_id, start=start, end=end)

        invoices = raw.get("invoices", [])
        count_total = len(invoices)
        count_ok = 0
        schema_fail = 0
        schematron_fail = 0
        pdfa_checks_ok = 0
        pdfa_checks_total = 0
        duration_ms = 0.0

        for invoice in invoices:
            validation = invoice.get("validation", {})
            
            schema_ok = validation.get("schema_ok", False)
            schematron_ok = validation.get("schematron_ok", False)

            if schema_ok and schematron_ok:
                count_ok += 1
            else:
                if not schema_ok:
                    schema_fail += 1
                if not schematron_ok:
                    schematron_fail += 1

            # PDF/A-Checks
            pdfa_checks = invoice.get("pdfa_checks")
            if pdfa_checks:
                pdfa_checks_total += 1
                if pdfa_checks.get("has_xmp") and pdfa_checks.get("has_af") and pdfa_checks.get("has_embedded"):
                    pdfa_checks_ok += 1

        duration_avg_ms = duration_ms / count_total if count_total > 0 else 0.0

        metrics = EInvoiceKpiMetrics(
            count_ok=count_ok,
            count_total=count_total,
            schema_fail=schema_fail,
            schematron_fail=schematron_fail,
            pdfa_checks_ok=pdfa_checks_ok,
            pdfa_checks_total=pdfa_checks_total,
            duration_ms=duration_ms,
            duration_avg_ms=duration_avg_ms,
        )

        metadata = dict(raw.get("metadata", {}))
        metadata["report_generated_at"] = now.isoformat()

        return EInvoiceKpiReport(
            tenant_id=tenant_id,
            report_date=report_date,
            timezone="Europe/Berlin",
            generated_at=now,
            metrics=metrics,
            metadata=metadata,
        )


def _report_json(report: EInvoiceKpiReport) -> dict[str, object]:
    """Konvertiere Report zu JSON-Dict."""
    metrics = report.metrics
    return {
        "tenant_id": report.tenant_id,
        "report_date": report.report_date.isoformat(),
        "timezone": report.timezone,
        "generated_at": report.generated_at.isoformat(),
        "metrics": {
            "count_ok": metrics.count_ok,
            "count_total": metrics.count_total,
            "schema_fail": metrics.schema_fail,
            "schematron_fail": metrics.schematron_fail,
            "pdfa_checks_ok": metrics.pdfa_checks_ok,
            "pdfa_checks_total": metrics.pdfa_checks_total,
            "duration_ms": metrics.duration_ms,
            "duration_avg_ms": metrics.duration_avg_ms,
        },
        "metadata": {k: _redact_pii(str(v)) if isinstance(v, str) else v for k, v in report.metadata.items()},
    }


def _report_markdown(report: EInvoiceKpiReport) -> str:
    """Konvertiere Report zu Markdown."""
    metrics = report.metrics
    lines = [
        f"# E-Invoice KPI Report — {report.report_date.isoformat()}",
        "",
        f"*Tenant:* `{report.tenant_id}`",
        f"*Timezone:* {report.timezone}",
        f"*Generated at:* {report.generated_at.isoformat()}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total Invoices | {metrics.count_total} |",
        f"| Validation OK | {metrics.count_ok} |",
        f"| Schema Failures | {metrics.schema_fail} |",
        f"| Schematron Failures | {metrics.schematron_fail} |",
        f"| PDF/A Checks OK | {metrics.pdfa_checks_ok} / {metrics.pdfa_checks_total} |",
        f"| Duration Avg (ms) | {metrics.duration_avg_ms:.2f} |",
    ]
    return "\n".join(lines) + "\n"


def discover_tenants(base_path: Path = ARTIFACT_ROOT) -> list[str]:
    """Entdecke verfügbare Tenants."""
    if not base_path.exists():
        return []
    return sorted([p.name for p in base_path.iterdir() if p.is_dir()])


def write_reports(
    report: EInvoiceKpiReport,
    base_path: Path = ARTIFACT_ROOT,
    dry_run: bool = False,
    write_summary: bool = True,
) -> tuple[Path, Path, Path | None]:
    """Schreibe KPI-Reports (JSON, MD, optional Summary)."""
    tenant_dir = base_path / report.tenant_id
    if not dry_run:
        tenant_dir.mkdir(parents=True, exist_ok=True)

    json_payload = _report_json(report)
    json_path = tenant_dir / f"{report.report_date.isoformat()}.json"
    md_path = tenant_dir / f"{report.report_date.isoformat()}.md"

    if not dry_run:
        json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        md_path.write_text(_report_markdown(report), encoding="utf-8")

    summary_path: Path | None = None
    if write_summary:
        summary_lines = [
            f"- Total invoices: {report.metrics.count_total}",
            f"- Validation OK: {report.metrics.count_ok}",
            f"- Schema failures: {report.metrics.schema_fail}",
            f"- Schematron failures: {report.metrics.schematron_fail}",
            f"- PDF/A checks OK: {report.metrics.pdfa_checks_ok} / {report.metrics.pdfa_checks_total}",
        ]
        summary_path = tenant_dir / f"{report.report_date.isoformat()}_summary.md"
        if not dry_run:
            write_markdown_summary(
                summary_path,
                heading="E-Invoice Daily Summary",
                lines=summary_lines,
            )

    return json_path, md_path, summary_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate daily E-Invoice KPIs")
    parser.add_argument("--tenant", help="Specific tenant UUID")
    parser.add_argument("--all-tenants", action="store_true", help="Process all tenants under artifacts")
    parser.add_argument("--date", help="Report date (YYYY-MM-DD) in Europe/Berlin timezone")
    parser.add_argument("--dry-run", action="store_true", help="Skip writing artefacts")
    parser.add_argument("--no-summary", action="store_true", help="Do not write summary markdown")
    parser.add_argument("--notify", action="store_true", help="Emit notification payload")
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

    tenants: list[str]
    if args.all_tenants:
        tenants = discover_tenants()
    else:
        tenant = args.tenant or os.environ.get("TENANT_DEFAULT")
        if not tenant:
            raise SystemExit("TENANT_DEFAULT not set and no --tenant provided")
        tenants = [tenant]

    data_source = LocalArtifactDataSource()
    aggregator = EInvoiceKpiAggregator(data_source)

    for tenant_id in tenants:
        report = aggregator.build_report(tenant_id, report_date=report_date)
        json_path, md_path, summary_path = write_reports(
            report,
            dry_run=args.dry_run,
            write_summary=not args.no_summary,
        )

        payload = NotificationPayload(
            title=f"E-Invoice KPIs {tenant_id} {report_date.isoformat()}",
            message=(
                f"Total: {report.metrics.count_total}, OK: {report.metrics.count_ok}, "
                f"Schema fails: {report.metrics.schema_fail}, Schematron fails: {report.metrics.schematron_fail}"
            ),
            details={
                "tenant_id": tenant_id,
                "report_date": report_date.isoformat(),
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "summary_path": str(summary_path) if summary_path else None,
                "metrics": _report_json(report)["metrics"],
            },
        )

        if args.notify:
            slack_sent = maybe_emit_slack(payload)
            if not slack_sent:
                emit_stdout(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

