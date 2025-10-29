"""Tests for tools.operate.kpi_engine — auto-generated via PDD."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tools.operate.kpi_engine import KpiAggregator, LocalArtifactDataSource


@pytest.fixture
def tenant_setup(tmp_path: Path) -> tuple[str, Path, Path]:
    tenant_id = "tenant-test"
    base = tmp_path / "artifacts" / "reports" / "mahnwesen"
    tenant_dir = base / tenant_id
    (tenant_dir / "audit").mkdir(parents=True)
    (tenant_dir / "outbox").mkdir()
    (tenant_dir / "ops").mkdir()
    return tenant_id, base, tenant_dir


def test_cycle_time_median_hours(tenant_setup: tuple[str, Path, Path]) -> None:
    tenant_id, base, tenant_dir = tenant_setup

    created_at = datetime(2025, 10, 28, 7, tzinfo=UTC)
    second_created = created_at + timedelta(hours=1)
    approvals = {
        "records": [
            {
                "tenant_id": tenant_id,
                "notice_id": "NOTICE-1",
                "invoice_id": "INV-1",
                "stage": 2,
                "idempotency_key": "key-1",
                "status": "sent",
                "requester": "operate-cli",
                "created_at": created_at.isoformat(),
                "updated_at": (created_at + timedelta(hours=2)).isoformat(),
            },
            {
                "tenant_id": tenant_id,
                "notice_id": "NOTICE-2",
                "invoice_id": "INV-2",
                "stage": 3,
                "idempotency_key": "key-2",
                "status": "sent",
                "requester": "operate-cli",
                "created_at": second_created.isoformat(),
                "updated_at": (second_created + timedelta(hours=4)).isoformat(),
            },
        ]
    }
    (tenant_dir / "audit" / "approvals.json").write_text(
        json.dumps(approvals, indent=2), encoding="utf-8"
    )

    (tenant_dir / "outbox" / "sent.json").write_text(
        json.dumps({"keys": ["abc", "def"]}), encoding="utf-8"
    )

    blocklist = {
        "entries": {
            "hash-hard": {"status": "hard", "attempt_timestamps": []},
            "hash-soft": {"status": "soft", "attempt_timestamps": []},
        }
    }
    (tenant_dir / "ops" / "blocklist.json").write_text(json.dumps(blocklist), encoding="utf-8")

    queue_metrics = {"retry_depth": 5, "dlq_depth": 0}
    (tenant_dir / "ops" / "queue_metrics.json").write_text(
        json.dumps(queue_metrics), encoding="utf-8"
    )

    data_source = LocalArtifactDataSource(base)
    aggregator = KpiAggregator(data_source)
    report = aggregator.build_report(tenant_id, report_date=date(2025, 10, 29), now=datetime(2025, 10, 29, 7, tzinfo=UTC))

    assert report.metrics.cycle_time_median_hours == 3.0
    assert report.metrics.hard_bounces == 1
    assert report.metrics.soft_bounces == 1
    assert report.metrics.retry_depth == 5
    assert report.timezone == "Europe/Berlin"


def test_cycle_time_note_when_missing(tenant_setup: tuple[str, Path, Path]) -> None:
    tenant_id, base, tenant_dir = tenant_setup

    (tenant_dir / "outbox" / "sent.json").write_text(
        json.dumps({"keys": ["only-key"]}), encoding="utf-8"
    )

    data_source = LocalArtifactDataSource(base)
    aggregator = KpiAggregator(data_source)
    report = aggregator.build_report(tenant_id, report_date=date(2025, 10, 29))

    assert report.metrics.cycle_time_median_hours is None
    assert report.metrics.cycle_time_note is not None
    assert report.metrics.notices_sent == 1

