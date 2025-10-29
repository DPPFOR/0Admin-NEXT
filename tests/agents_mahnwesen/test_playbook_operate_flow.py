"""Tests for DunningPlaybook operate flow — auto-generated via PDD."""

from unittest.mock import MagicMock

import pytest

from agents.mahnwesen.approval_store import ApprovalStore
from agents.mahnwesen.playbooks import DunningContext, DunningPlaybook
from agents.mahnwesen.providers import LocalOverdueProvider
from agents.mahnwesen.dto import DunningNotice


TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def approval_store(tmp_path) -> ApprovalStore:
    return ApprovalStore(base_path=tmp_path)


def _build_context(
    *,
    dry_run: bool,
    approval_store: ApprovalStore,
    requester: str = "pytest",
) -> DunningContext:
    return DunningContext(
        tenant_id=TENANT_ID,
        correlation_id="test-correlation",
        dry_run=dry_run,
        limit=10,
        approval_store=approval_store,
        overdue_provider=LocalOverdueProvider(),
        requester=requester,
    )


def test_run_once_blocks_stage2_without_approval(approval_store: ApprovalStore) -> None:
    context = _build_context(dry_run=True, approval_store=approval_store)
    playbook = DunningPlaybook(context.config)

    result = playbook.run_once(context)

    blocked = result.metadata.get("blocked_without_approval", [])
    prepared = result.metadata.get("dry_run_prepared", [])

    assert any(entry["stage"] == 2 for entry in blocked)
    assert result.events_dispatched == len(prepared)
    assert all(entry["stage"] == 1 for entry in prepared)


def test_run_once_dispatches_after_approval(monkeypatch, approval_store: ApprovalStore) -> None:
    # Initial preview to register pending approval
    preview_context = _build_context(dry_run=True, approval_store=approval_store)
    playbook = DunningPlaybook(preview_context.config)
    playbook.run_once(preview_context)

    # Approve stage 2 notice
    record = approval_store.get_by_notice(TENANT_ID, "NOTICE-INV-S2-001")
    assert record is not None
    approval_store.approve(
        tenant_id=TENANT_ID,
        notice_id=record.notice_id,
        stage=record.stage,
        approver="user2",
        comment="Freigabe",
        actor="user2",
        correlation_id="corr-id",
    )

    # Live run with patched Brevo and Outbox
    live_context = _build_context(dry_run=False, approval_store=approval_store, requester="runner")

    def _fake_send(notice: DunningNotice, context: DunningContext):
        class Response:
            success = True
            message_id = f"msg-{notice.notice_id}"
            error = None

        return Response()

    monkeypatch.setattr(DunningPlaybook, "_send_via_brevo", lambda self, notice, ctx: _fake_send(notice, ctx))

    fake_outbox = MagicMock()
    fake_outbox.check_duplicate_event.return_value = False
    fake_outbox.publish_dunning_issued.return_value = True
    live_context.outbox_client = fake_outbox

    result = playbook.run_once(live_context)

    dispatch_records = result.metadata.get("dispatch_records", [])
    stage_counts = {entry["stage"]: entry for entry in dispatch_records}

    assert 1 in stage_counts
    assert 2 in stage_counts
    assert result.events_dispatched >= 3

    approval_entries = [entry for entry in result.metadata.get("approval_records", []) if entry.get("status") == "sent"]
    assert any(entry["stage"] == 2 for entry in approval_entries)

