"""Daily KPI aggregation for Mahnwesen (07:30 Europe/Berlin).

The module is designed for production use. Data access is abstracted
through ``KpiDataSource`` so that live integrations (e.g. Brevo, DB) can
be added without touching the aggregation logic. The default
``LocalArtifactDataSource`` consumes the artefacts produced by the
operate tooling (approvals, blocklists, sent cache).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo

from agents.mahnwesen.providers import LocalOverdueProvider

from tools.operate.notifiers import (
    NotificationPayload,
    emit_stdout,
    maybe_emit_slack,
    write_markdown_summary,
)

TZ_EUROPE_BERLIN = ZoneInfo("Europe/Berlin")
ARTIFACT_ROOT = Path("artifacts/reports/mahnwesen")


@dataclass
class NoticeLifecycle:
    """Lifecycle information for a single notice."""

    notice_id: str
    stage: int
    status: str
    requested_at: datetime | None
    sent_at: datetime | None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class QueueMetrics:
    """Current queue metrics used for KPIs."""

    retry_depth: int = 0
    dlq_depth: int = 0


@dataclass
class RawKpiData:
    """Container returned by data sources."""

    lifecycles: list[NoticeLifecycle] = field(default_factory=list)
    overdue_total: int = 0
    queue_metrics: QueueMetrics = field(default_factory=QueueMetrics)
    outbox_sent_count: int = 0
    hard_bounces: int = 0
    soft_bounces: int = 0
    escalations: int = 0
    errors: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


class KpiDataSource(Protocol):
    """Protocol that any KPI data source must implement."""

    def load(self, tenant_id: str, start: datetime, end: datetime) -> RawKpiData:
        ...


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


class LocalArtifactDataSource:
    """Default data source using local operate artefacts."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or ARTIFACT_ROOT
        self.overdue_provider = LocalOverdueProvider()

    def load(self, tenant_id: str, start: datetime, end: datetime) -> RawKpiData:
        tenant_dir = self.base_path / tenant_id
        lifecycles = []
        metadata: dict[str, object] = {}

        approvals_file = tenant_dir / "audit" / "approvals.json"
        if approvals_file.exists():
            data = json.loads(approvals_file.read_text(encoding="utf-8"))
            raw_records = data.get("records", [])
            if isinstance(raw_records, dict):
                iterable = raw_records.values()
            elif isinstance(raw_records, list):
                iterable = raw_records
            else:
                iterable = []

            for rec in iterable:
                if not isinstance(rec, dict):
                    continue
                if rec.get("tenant_id") != tenant_id:
                    continue
                status = str(rec.get("status", "pending"))
                reason = rec.get("reason")
                errors_list: list[str] = []
                status_lower = status.lower()
                if status_lower == "failed":
                    errors_list = [str(reason or "dispatch failed")]
                elif status_lower == "rejected":
                    errors_list = [str(reason or "rejected")]

                lifecycles.append(
                    NoticeLifecycle(
                        notice_id=str(rec.get("notice_id", "")),
                        stage=int(rec.get("stage", 0) or 0),
                        status=status,
                        requested_at=_parse_datetime(rec.get("created_at")),
                        sent_at=_parse_datetime(rec.get("updated_at"))
                        if rec.get("status") == "sent"
                        else None,
                        errors=errors_list,
                        metadata={
                            "idempotency_key": str(rec.get("idempotency_key", "")),
                            "requester": str(rec.get("requester", "")),
                            "reason": str(reason) if reason else "",
                        },
                    )
                )

        outbox_file = tenant_dir / "outbox" / "sent.json"
        outbox_sent_count = 0
        if outbox_file.exists():
            outbox_data = json.loads(outbox_file.read_text(encoding="utf-8"))
            outbox_keys: list[str] = outbox_data.get("keys", [])
            outbox_sent_count = len({k for k in outbox_keys})
            metadata["outbox_keys"] = outbox_keys

        blocklist_file = tenant_dir / "ops" / "blocklist.json"
        hard_bounces = 0
        soft_bounces = 0
        if blocklist_file.exists():
            block_data = json.loads(blocklist_file.read_text(encoding="utf-8"))
            entries: dict[str, dict[str, object]] = block_data.get("entries", {})
            for entry in entries.values():
                status = entry.get("status")
                if status == "hard":
                    hard_bounces += 1
                elif status == "soft":
                    soft_bounces += 1
            metadata["blocklist_entries"] = len(entries)

        escalate_count = sum(1 for item in lifecycles if item.stage >= 3)

        queue_metrics = QueueMetrics()
        queue_file = tenant_dir / "ops" / "queue_metrics.json"
        if queue_file.exists():
            queue_data = json.loads(queue_file.read_text(encoding="utf-8"))
            queue_metrics.retry_depth = int(queue_data.get("retry_depth", 0))
            queue_metrics.dlq_depth = int(queue_data.get("dlq_depth", 0))

        overdue_total = len(self.overdue_provider.load_overdue_invoices(tenant_id, limit=None))

        metadata.setdefault("notes", []).append(
            "LocalArtifactDataSource used – swapable via KpiDataSource interface"
        )

        return RawKpiData(
            lifecycles=lifecycles,
            overdue_total=overdue_total,
            queue_metrics=queue_metrics,
            outbox_sent_count=outbox_sent_count,
            hard_bounces=hard_bounces,
            soft_bounces=soft_bounces,
            escalations=escalate_count,
            errors=sum(len(item.errors) for item in lifecycles),
            metadata=metadata,
        )


@dataclass
class KpiMetrics:
    overdue_total: int
    notices_created: int
    notices_sent: int
    errors: int
    hard_bounces: int
    soft_bounces: int
    escalations: int
    retry_depth: int
    dlq_depth: int
    error_rate: float
    cycle_time_median_hours: float | None
    cycle_time_note: str | None = None


@dataclass
class KpiReport:
    tenant_id: str
    report_date: date
    timezone: str
    generated_at: datetime
    metrics: KpiMetrics
    metadata: dict[str, object] = field(default_factory=dict)


class KpiAggregator:
    """Aggregate raw data into report metrics."""

    def __init__(self, data_source: KpiDataSource) -> None:
        self.data_source = data_source

    def build_report(
        self,
        tenant_id: str,
        report_date: date,
        now: datetime | None = None,
    ) -> KpiReport:
        now = now or datetime.now(UTC)
        start = datetime.combine(report_date, datetime.min.time(), tzinfo=TZ_EUROPE_BERLIN).astimezone(UTC)
        end = (start + timedelta(days=1))

        raw = self.data_source.load(tenant_id, start=start, end=end)

        notices_created = max(len(raw.lifecycles), raw.outbox_sent_count)
        notices_sent = raw.outbox_sent_count

        cycle_times = [
            (lc.sent_at - lc.requested_at).total_seconds() / 3600
            for lc in raw.lifecycles
            if lc.requested_at and lc.sent_at and lc.sent_at >= lc.requested_at
        ]

        cycle_note: str | None = None
        cycle_median: float | None = None
        if cycle_times:
            cycle_median = round(statistics.median(cycle_times), 2)
        else:
            cycle_note = "No lifecycle pairs available (pending approvals or Stage 1 without audit)."

        total_events = max(1, notices_created)
        error_rate = round(raw.errors / total_events, 4)

        metrics = KpiMetrics(
            overdue_total=raw.overdue_total,
            notices_created=notices_created,
            notices_sent=notices_sent,
            errors=raw.errors,
            hard_bounces=raw.hard_bounces,
            soft_bounces=raw.soft_bounces,
            escalations=raw.escalations,
            retry_depth=raw.queue_metrics.retry_depth,
            dlq_depth=raw.queue_metrics.dlq_depth,
            error_rate=error_rate,
            cycle_time_median_hours=cycle_median,
            cycle_time_note=cycle_note,
        )

        metadata = dict(raw.metadata)
        metadata["cycle_samples"] = len(cycle_times)

        return KpiReport(
            tenant_id=tenant_id,
            report_date=report_date,
            timezone="Europe/Berlin",
            generated_at=now,
            metrics=metrics,
            metadata=metadata,
        )


def _report_json(report: KpiReport) -> dict[str, object]:
    metrics = report.metrics
    payload = {
        "tenant_id": report.tenant_id,
        "report_date": report.report_date.isoformat(),
        "timezone": report.timezone,
        "generated_at": report.generated_at.isoformat(),
        "metrics": {
            "overdue_total": metrics.overdue_total,
            "notices_created": metrics.notices_created,
            "notices_sent": metrics.notices_sent,
            "errors": metrics.errors,
            "hard_bounces": metrics.hard_bounces,
            "soft_bounces": metrics.soft_bounces,
            "escalations": metrics.escalations,
            "retry_depth": metrics.retry_depth,
            "dlq_depth": metrics.dlq_depth,
            "error_rate": metrics.error_rate,
            "cycle_time_median_hours": metrics.cycle_time_median_hours,
            "cycle_time_note": metrics.cycle_time_note,
        },
        "metadata": report.metadata,
    }
    return payload


def _report_markdown(report: KpiReport) -> str:
    metrics = report.metrics
    lines = [
        f"# Mahnwesen KPI Report — {report.report_date.isoformat()}",
        "",
        f"*Tenant:* `{report.tenant_id}`",
        f"*Timezone:* {report.timezone}",
        f"*Generated at:* {report.generated_at.isoformat()}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Overdue Total | {metrics.overdue_total} |",
        f"| Notices Created | {metrics.notices_created} |",
        f"| Notices Sent | {metrics.notices_sent} |",
        f"| Errors | {metrics.errors} |",
        f"| Hard Bounces | {metrics.hard_bounces} |",
        f"| Soft Bounces | {metrics.soft_bounces} |",
        f"| Escalations (S3) | {metrics.escalations} |",
        f"| Retry Depth | {metrics.retry_depth} |",
        f"| DLQ Depth | {metrics.dlq_depth} |",
        f"| Error Rate | {metrics.error_rate:.4f} |",
        f"| Cycle Time Median (hours) | {metrics.cycle_time_median_hours if metrics.cycle_time_median_hours is not None else 'n/a'} |",
    ]
    if metrics.cycle_time_note:
        lines += ["", f"> {metrics.cycle_time_note}"]
    return "\n".join(lines) + "\n"


def discover_tenants(base_path: Path = ARTIFACT_ROOT) -> list[str]:
    if not base_path.exists():
        return []
    return sorted([p.name for p in base_path.iterdir() if p.is_dir()])


def write_reports(
    report: KpiReport,
    base_path: Path = ARTIFACT_ROOT,
    dry_run: bool = False,
    write_summary: bool = True,
) -> tuple[Path, Path, Path | None]:
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
            f"- Notices sent: {report.metrics.notices_sent}",
            f"- Errors: {report.metrics.errors}",
            f"- Hard bounces: {report.metrics.hard_bounces}",
            f"- DLQ depth: {report.metrics.dlq_depth}",
        ]
        summary_path = tenant_dir / f"{report.report_date.isoformat()}_summary.md"
        if not dry_run:
            write_markdown_summary(
                summary_path,
                heading="Mahnwesen Daily Summary",
                lines=summary_lines,
            )

    return json_path, md_path, summary_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate daily Mahnwesen KPIs")
    parser.add_argument("--tenant", help="Specific tenant UUID")
    parser.add_argument("--all-tenants", action="store_true", help="Process all tenants under artifacts")
    parser.add_argument("--date", help="Report date (YYYY-MM-DD) in Europe/Berlin timezone")
    parser.add_argument("--dry-run", action="store_true", help="Skip writing artefacts")
    parser.add_argument("--no-summary", action="store_true", help="Do not write summary markdown")
    parser.add_argument("--notify", action="store_true", help="Emit notification payload")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.tenant and args.all_tenants:
        raise SystemExit("--tenant and --all-tenants are mutually exclusive")

    if args.date:
        report_date = date.fromisoformat(args.date)
    else:
        now_local = datetime.now(TZ_EUROPE_BERLIN)
        report_date = now_local.date()

    tenants: Iterable[str]
    if args.all_tenants:
        tenants = discover_tenants()
    else:
        tenant = args.tenant or os.environ.get("TENANT_DEFAULT")
        if not tenant:
            raise SystemExit("TENANT_DEFAULT not set and no --tenant provided")
        tenants = [tenant]

    data_source = LocalArtifactDataSource()
    aggregator = KpiAggregator(data_source)

    for tenant_id in tenants:
        report = aggregator.build_report(tenant_id, report_date=report_date)
        json_path, md_path, summary_path = write_reports(
            report,
            dry_run=args.dry_run,
            write_summary=not args.no_summary,
        )

        payload = NotificationPayload(
            title=f"KPIs {tenant_id} {report_date.isoformat()}",
            message=(
                f"Notices sent: {report.metrics.notices_sent}, errors: {report.metrics.errors}, "
                f"hard bounces: {report.metrics.hard_bounces}"
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

