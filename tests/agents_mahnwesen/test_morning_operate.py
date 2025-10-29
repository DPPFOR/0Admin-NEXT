"""Tests for morning operate orchestrator — auto-generated via PDD."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

from tools.operate.canary_rollout import apply_rollout
from tools.operate.morning_operate import run_morning_for_tenant


@pytest.fixture
def fixture_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    tenant = "00000000-0000-0000-0000-000000000001"
    base = tmp_path
    (base / tenant / "operate").mkdir(parents=True, exist_ok=True)
    (base / tenant / "ops").mkdir(exist_ok=True)
    # Baseline operate state
    (base / tenant / "operate" / "operate_state.json").write_text(
        json.dumps({"kill_switch": False, "rollout_percentage": 10}),
        encoding="utf-8",
    )
    # Ensure LocalArtifactDataSource can resolve samples (uses repo files)
    monkeypatch.chdir(Path.cwd())
    return tenant, base


def _seed_positive_kpi(base: Path, tenant: str) -> None:
    tenant_dir = base / tenant
    approvals = {
        "records": [
            {
                "tenant_id": tenant,
                "notice_id": f"NOTICE-{idx}",
                "invoice_id": f"INV-{idx}",
                "stage": 1,
                "idempotency_key": f"key-{idx}",
                "status": "sent",
                "requester": "operate-cli",
                "created_at": "2025-10-29T07:00:00+00:00",
                "updated_at": "2025-10-29T07:05:00+00:00",
            }
            for idx in range(3)
        ]
    }
    (tenant_dir / "audit").mkdir(exist_ok=True)
    (tenant_dir / "audit" / "approvals.json").write_text(json.dumps(approvals), encoding="utf-8")

    outbox = {"keys": [f"key-{idx}" for idx in range(3)]}
    (tenant_dir / "outbox").mkdir(exist_ok=True)
    (tenant_dir / "outbox" / "sent.json").write_text(json.dumps(outbox), encoding="utf-8")

    blocklist = {"entries": {}}
    (tenant_dir / "ops" / "blocklist.json").write_text(json.dumps(blocklist), encoding="utf-8")


def test_morning_operate_dry_run_idempotent(fixture_paths: tuple[str, Path]) -> None:
    tenant, base = fixture_paths
    result = run_morning_for_tenant(tenant, date(2025, 10, 29), dry_run=True, base_path=base)

    summary_path = Path(result["summary_md"])
    assert summary_path.exists()
    content = summary_path.read_text(encoding="utf-8")
    assert "DRY-RUN" in content
    assert result["rollout_changed"] is False

    # Operate state unchanged
    state_path = base / tenant / "operate" / "operate_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["rollout_percentage"] == 10


def test_morning_operate_live_rollout_progression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = "00000000-0000-0000-0000-000000000001"
    base = tmp_path
    (base / tenant / "operate").mkdir(parents=True, exist_ok=True)
    (base / tenant / "ops").mkdir(exist_ok=True)
    (base / tenant / "operate" / "operate_state.json").write_text(
        json.dumps({"kill_switch": False, "rollout_percentage": 10}), encoding="utf-8"
    )
    _seed_positive_kpi(base, tenant)

    # Override thresholds to permissive values
    monkeypatch.setenv("CANARY_THRESHOLD_ERROR_RATE", "0.5")
    monkeypatch.setenv("CANARY_THRESHOLD_HARD_BOUNCE_RATE", "1.0")

    result = run_morning_for_tenant(tenant, date(2025, 10, 29), dry_run=False, base_path=base)
    assert result["decision"] in {"GO_25", "GO_50", "GO_100"}
    assert result["rollout_changed"] is True

    state_path = base / tenant / "operate" / "operate_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["rollout_percentage"] >= 25

    # Second run without new KPI should not regress
    second = run_morning_for_tenant(tenant, date(2025, 10, 29), dry_run=False, base_path=base)
    assert Path(second["summary_md"]).exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["rollout_percentage"] >= state["rollout_percentage"]

