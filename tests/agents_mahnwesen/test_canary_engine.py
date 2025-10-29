"""Tests for canary decision engine — auto-generated via PDD."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tools.operate.canary_engine import generate_decision, write_decision, determine_next_action


@pytest.fixture
def base_setup(tmp_path: Path) -> tuple[str, Path]:
    tenant = "tenant-123"
    tenant_dir = tmp_path / tenant
    tenant_dir.mkdir(parents=True)
    (tenant_dir / "operate").mkdir()
    (tenant_dir / "ops").mkdir()
    return tenant, tmp_path


def _write_kpi(tenant_dir: Path, report_date: str, notices_sent: int, errors: int, hard_bounces: int, retry_depth: int = 1, dlq_depth: int = 0) -> None:
    data = {
        "metrics": {
            "notices_sent": notices_sent,
            "errors": errors,
            "hard_bounces": hard_bounces,
            "retry_depth": retry_depth,
            "dlq_depth": dlq_depth,
            "cycle_time_median_hours": 1.2,
        }
    }
    (tenant_dir / f"{report_date}.json").write_text(json.dumps(data), encoding="utf-8")


def _write_blocklist(tenant_dir: Path, hard: int, soft: int = 0) -> None:
    entries = {}
    for idx in range(hard):
        entries[f"hard-{idx}"] = {"status": "hard"}
    for idx in range(soft):
        entries[f"soft-{idx}"] = {"status": "soft"}
    ops_dir = tenant_dir / "ops"
    (ops_dir / "blocklist.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")


def _write_state(tenant_dir: Path, rollout: int = 10, kill_switch: bool = False) -> None:
    operate_dir = tenant_dir / "operate"
    operate_dir.mkdir(exist_ok=True)
    state = {"rollout_percentage": rollout, "kill_switch": kill_switch}
    (operate_dir / "operate_state.json").write_text(json.dumps(state), encoding="utf-8")


def test_generate_decision_go_25(base_setup: tuple[str, Path]) -> None:
    tenant, base = base_setup
    tenant_dir = base / tenant
    report_date = date(2025, 10, 29)
    _write_kpi(tenant_dir, report_date.isoformat(), notices_sent=5, errors=0, hard_bounces=0)
    _write_blocklist(tenant_dir, hard=0)
    _write_state(tenant_dir, rollout=10, kill_switch=False)

    decision = generate_decision(tenant, report_date, base_path=base)
    assert decision["recommended_action"] == "GO_25"
    assert decision["metrics"]["error_rate"] == 0.0


def test_generate_decision_hold_due_to_errors(base_setup: tuple[str, Path]) -> None:
    tenant, base = base_setup
    tenant_dir = base / tenant
    report_date = date(2025, 10, 29)
    _write_kpi(tenant_dir, report_date.isoformat(), notices_sent=5, errors=1, hard_bounces=0)
    _write_blocklist(tenant_dir, hard=0)
    _write_state(tenant_dir, rollout=25)

    decision = generate_decision(tenant, report_date, base_path=base)
    assert decision["recommended_action"] == "HOLD"
    assert any("Error rate" in reason for reason in decision["reasons"])


def test_write_decision_creates_files(base_setup: tuple[str, Path], tmp_path: Path) -> None:
    tenant, base = base_setup
    tenant_dir = base / tenant
    report_date = date(2025, 10, 29)
    _write_kpi(tenant_dir, report_date.isoformat(), notices_sent=5, errors=0, hard_bounces=0)
    _write_blocklist(tenant_dir, hard=0)
    _write_state(tenant_dir, rollout=10)

    decision = generate_decision(tenant, report_date, base_path=base)
    now = datetime.now(UTC)
    json_path, md_path = write_decision(tenant, decision, report_date, now, base_path=base)
    assert json_path.exists()
    assert md_path.exists()

