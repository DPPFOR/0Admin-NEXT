"""Tests for operate tooling — auto-generated via PDD."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.operate.alert_emitter import ALERT_THRESHOLDS, build_alert
from tools.operate.canary_decision import CanaryThresholds, evaluate_canary
from tools.operate.kill_switch import apply_kill_switch


def test_build_alert_uses_threshold_and_sets_severity() -> None:
    payload = build_alert(
        tenant_id="tenant",
        metric="error_rate",
        value=0.05,
        trace_id="trace-1",
    )
    assert payload["metric"] == "error_rate"
    assert payload["threshold"] == ALERT_THRESHOLDS["error_rate"]
    assert payload["severity"] == "critical"
    assert "Exceeded" in payload["message"].capitalize() or "exceeded" in payload["message"].lower()


@pytest.mark.parametrize(
    "success,error,dlq,bounce,expected",
    [
        (0.98, 0.005, 0, 0.01, "GO_25"),
        (0.94, 0.020, 2, 0.07, "HOLD"),
    ],
)
def test_evaluate_canary(success, error, dlq, bounce, expected) -> None:
    decision, reasons = evaluate_canary(
        success_rate=success,
        error_rate=error,
        dlq_depth=dlq,
        hard_bounce_rate=bounce,
        thresholds=CanaryThresholds(),
    )
    assert decision == expected
    if decision == "HOLD":
        assert reasons and any("exceeds" in r.lower() or "below" in r.lower() for r in reasons)


def test_apply_kill_switch_idempotent(tmp_path: Path) -> None:
    tenant = "tenant-test"
    payload1 = apply_kill_switch(
        tenant_id=tenant,
        reason="Backout test",
        trace_id="trace-1",
        state_dir=tmp_path,
    )
    payload2 = apply_kill_switch(
        tenant_id=tenant,
        reason="New reason should not replace",
        trace_id="trace-2",
        state_dir=tmp_path,
    )

    assert payload1["kill_switch"] is True
    assert payload2["kill_switch"] is True
    # original reason preserved due to idempotency
    assert payload2["reason"] == "Backout test"
    assert payload2["trace_id"] == "trace-1"

