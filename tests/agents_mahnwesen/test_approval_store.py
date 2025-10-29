"""Tests for ApprovalStore — auto-generated via PDD."""

from datetime import UTC, datetime

import pytest

from agents.mahnwesen.approval_store import ApprovalRecord, ApprovalStore
from agents.mahnwesen.dto import DunningStage


TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def store(tmp_path) -> ApprovalStore:
    return ApprovalStore(base_path=tmp_path)


def _create_pending(store: ApprovalStore) -> ApprovalRecord:
    return store.register_pending(
        tenant_id=TENANT_ID,
        notice_id="NOTICE-INV-S2-001",
        invoice_id="INV-S2-001",
        stage=DunningStage.STAGE_2,
        idempotency_key="abc123",
        requester="tester",
        reason="Initial preview",
    )


def test_register_pending_is_idempotent(store: ApprovalStore) -> None:
    first = _create_pending(store)
    second = _create_pending(store)

    assert first.notice_id == second.notice_id
    assert second.status == "pending"
    assert second.reason == "Initial preview"


def test_approve_updates_record(store: ApprovalStore) -> None:
    _create_pending(store)
    record = store.approve(
        tenant_id=TENANT_ID,
        notice_id="NOTICE-INV-S2-001",
        stage=DunningStage.STAGE_2,
        approver="user2",
        comment="Looks good",
        actor="user2",
        correlation_id="corr-id",
    )

    assert record.status == "approved"
    assert record.approver == "user2"
    assert record.comment == "Looks good"


def test_reject_updates_record(store: ApprovalStore) -> None:
    _create_pending(store)
    record = store.reject(
        tenant_id=TENANT_ID,
        notice_id="NOTICE-INV-S2-001",
        stage=DunningStage.STAGE_2,
        approver="user3",
        comment="Incorrect data",
        actor="user3",
        correlation_id="corr-id",
    )

    assert record.status == "rejected"
    assert record.comment == "Incorrect data"


def test_mark_sent_persists_status(store: ApprovalStore) -> None:
    _create_pending(store)
    store.approve(
        tenant_id=TENANT_ID,
        notice_id="NOTICE-INV-S2-001",
        stage=DunningStage.STAGE_2,
        approver="user2",
        comment="ok",
        actor="user2",
        correlation_id="corr-id",
    )
    store.mark_sent(TENANT_ID, "NOTICE-INV-S2-001", DunningStage.STAGE_2)

    record = store.get_by_notice(TENANT_ID, "NOTICE-INV-S2-001")
    assert record is not None
    assert record.status == "sent"


def test_get_by_notice_returns_none_when_missing(store: ApprovalStore) -> None:
    assert store.get_by_notice(TENANT_ID, "UNKNOWN") is None

