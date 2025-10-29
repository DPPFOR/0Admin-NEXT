"""Tests for tools.operate.bounce_reconcile — auto-generated via PDD."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.operate.bounce_reconcile import BounceReconciler


def _write_inbox(path: Path, events: list[dict[str, object]]) -> None:
    payload = {"events": events}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_soft_bounces_promote_to_hard(tmp_path: Path) -> None:
    tenant_id = "tenant-bounce"
    base = tmp_path / "artifacts" / "reports" / "mahnwesen"
    ops_dir = base / tenant_id / "ops"
    ops_dir.mkdir(parents=True)

    start = datetime(2025, 10, 29, 6, tzinfo=UTC)
    events = []
    for idx in range(3):
        events.append(
            {
                "event_id": f"evt-{idx}",
                "recipient_hash": "hash-1",
                "bounce_type": "soft",
                "occurred_at": (start + timedelta(hours=idx)).isoformat(),
                "notice_id": f"NOTICE-{idx}",
                "stage": "S1",
                "reason": "Mailbox full",
            }
        )

    _write_inbox(ops_dir / "bounce_inbox.json", events)

    reconciler = BounceReconciler(tenant_id, base)
    result = reconciler.process()

    blocklist = json.loads((ops_dir / "blocklist.json").read_text(encoding="utf-8"))
    entry = blocklist["entries"]["hash-1"]

    assert entry["status"] == "hard"
    assert len(entry["attempt_timestamps"]) == 3
    assert result.actions[-1]["action"] == "promote_hard"


def test_reconcile_idempotent(tmp_path: Path) -> None:
    tenant_id = "tenant-idem"
    base = tmp_path / "artifacts" / "reports" / "mahnwesen"
    ops_dir = base / tenant_id / "ops"
    ops_dir.mkdir(parents=True)

    event_time = datetime(2025, 10, 29, 7, tzinfo=UTC).isoformat()
    _write_inbox(
        ops_dir / "bounce_inbox.json",
        [
            {
                "event_id": "evt-1",
                "recipient_hash": "hash-x",
                "bounce_type": "hard",
                "occurred_at": event_time,
                "notice_id": "NOTICE-1",
                "stage": "S2",
                "reason": "Suppressed",
            }
        ],
    )

    reconciler = BounceReconciler(tenant_id, base)
    first_result = reconciler.process()
    blocklist_content = (ops_dir / "blocklist.json").read_text(encoding="utf-8")

    assert first_result.actions[0]["action"] == "block_hard"

    second_result = reconciler.process()
    assert second_result.actions == []

    inbox_payload = json.loads((ops_dir / "bounce_inbox.json").read_text(encoding="utf-8"))
    assert inbox_payload == {"events": []}

    assert json.loads((ops_dir / "blocklist.json").read_text(encoding="utf-8")) == json.loads(blocklist_content)

