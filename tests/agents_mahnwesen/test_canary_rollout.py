"""Tests for canary rollout controller — auto-generated via PDD."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.operate.canary_rollout import apply_rollout, load_operate_state, persist_state


@pytest.fixture
def tenant_setup(tmp_path: Path) -> tuple[str, Path, Path]:
    tenant = "tenant-abc"
    base = tmp_path
    operate_dir = base / tenant / "operate"
    operate_dir.mkdir(parents=True)
    state = {"rollout_percentage": 10, "kill_switch": False}
    (operate_dir / "operate_state.json").write_text(json.dumps(state), encoding="utf-8")
    canary_dir = base / tenant / "canary"
    canary_dir.mkdir(exist_ok=True)
    return tenant, base, canary_dir


def _write_decision(path: Path, action: str, reasons: list[str]) -> Path:
    decision = {
        "tenant_id": "tenant-abc",
        "recommended_action": action,
        "reasons": reasons,
        "report_date": "2025-10-29",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    file_path = path / "2025-10-29_0800_decision.json"
    file_path.write_text(json.dumps(decision), encoding="utf-8")
    return file_path


def test_apply_rollout_step_up(tenant_setup: tuple[str, Path, Path]) -> None:
    tenant, base, canary_dir = tenant_setup
    decision_path = _write_decision(canary_dir, "GO_25", ["All thresholds satisfied"])

    result = apply_rollout(tenant, json.loads(decision_path.read_text()), "trace-1", base_path=base)
    assert result["after"]["rollout_percentage"] == 25
    assert result["after"]["kill_switch"] is False
    assert result["changed"] is True

    # Applying same decision again should be idempotent
    result_again = apply_rollout(tenant, json.loads(decision_path.read_text()), "trace-2", base_path=base)
    assert result_again["changed"] is False


def test_apply_rollout_backout(tenant_setup: tuple[str, Path, Path]) -> None:
    tenant, base, canary_dir = tenant_setup
    decision_path = _write_decision(canary_dir, "BACKOUT", ["Hard bounce spike"])

    result = apply_rollout(tenant, json.loads(decision_path.read_text()), "trace-backout", base_path=base)
    assert result["after"]["kill_switch"] is True
    assert result["after"]["rollout_percentage"] == 10

