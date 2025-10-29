"""Persistent approval state management for Mahnwesen Operate-Flows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from .dto import DunningStage


@dataclass
class ApprovalRecord:
    """Represents the approval state for a notice."""

    tenant_id: str
    notice_id: str
    invoice_id: str
    stage: DunningStage
    idempotency_key: str
    status: str = "pending"  # pending|approved|rejected|sent
    requester: str = "system"
    approver: str | None = None
    comment: str | None = None
    actor: str | None = None
    reason: str | None = None
    correlation_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "notice_id": self.notice_id,
            "invoice_id": self.invoice_id,
            "stage": self.stage.value,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "requester": self.requester,
            "approver": self.approver,
            "comment": self.comment,
            "actor": self.actor,
            "reason": self.reason,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRecord":
        return cls(
            tenant_id=data["tenant_id"],
            notice_id=data["notice_id"],
            invoice_id=data["invoice_id"],
            stage=DunningStage(data["stage"]),
            idempotency_key=data["idempotency_key"],
            status=data.get("status", "pending"),
            requester=data.get("requester", "system"),
            approver=data.get("approver"),
            comment=data.get("comment"),
            actor=data.get("actor"),
            reason=data.get("reason"),
            correlation_id=data.get("correlation_id"),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
        )


class ApprovalStore:
    """JSON-backed persistence for MVR approvals."""

    def __init__(self, base_path: Path | str = Path("artifacts/reports/mahnwesen")):
        self.base_path = Path(base_path)
        self._cache: dict[str, dict[str, ApprovalRecord]] = {}

    def register_pending(
        self,
        *,
        tenant_id: str,
        notice_id: str,
        invoice_id: str,
        stage: DunningStage,
        idempotency_key: str,
        requester: str,
        reason: str | None = None,
        correlation_id: str | None = None,
    ) -> ApprovalRecord:
        records = self._load_tenant(tenant_id)
        key = self._key(idempotency_key)
        record = records.get(key)

        if record is None:
            record = ApprovalRecord(
                tenant_id=tenant_id,
                notice_id=notice_id,
                invoice_id=invoice_id,
                stage=stage,
                idempotency_key=idempotency_key,
                requester=requester,
                reason=reason,
                correlation_id=correlation_id,
            )
            records[key] = record
            self._persist(tenant_id)
        else:
            # keep existing record but refresh reason/status if still pending
            if record.status == "pending":
                record.reason = reason or record.reason
                record.correlation_id = correlation_id or record.correlation_id
                record.updated_at = datetime.now(UTC).isoformat()
                self._persist(tenant_id)

        return record

    def approve(
        self,
        *,
        tenant_id: str,
        notice_id: str,
        stage: DunningStage,
        approver: str,
        comment: str,
        actor: str,
        correlation_id: str,
    ) -> ApprovalRecord:
        record = self._get_required(tenant_id, notice_id, stage)
        record.status = "approved"
        record.approver = approver
        record.comment = comment
        record.actor = actor
        record.correlation_id = correlation_id
        record.updated_at = datetime.now(UTC).isoformat()
        self._persist(tenant_id)
        return record

    def reject(
        self,
        *,
        tenant_id: str,
        notice_id: str,
        stage: DunningStage,
        approver: str,
        comment: str,
        actor: str,
        correlation_id: str,
    ) -> ApprovalRecord:
        record = self._get_required(tenant_id, notice_id, stage)
        record.status = "rejected"
        record.approver = approver
        record.comment = comment
        record.actor = actor
        record.correlation_id = correlation_id
        record.updated_at = datetime.now(UTC).isoformat()
        self._persist(tenant_id)
        return record

    def mark_sent(self, tenant_id: str, notice_id: str, stage: DunningStage) -> None:
        record = self._get_optional(tenant_id, notice_id, stage)
        if record:
            record.status = "sent"
            record.updated_at = datetime.now(UTC).isoformat()
            self._persist(tenant_id)

    def can_send(
        self, tenant_id: str, invoice_id: str, notice_id: str, stage: DunningStage, idempotency_key: str
    ) -> tuple[bool, str | None, ApprovalRecord | None]:
        records = self._load_tenant(tenant_id)
        key = self._key(idempotency_key)
        record = records.get(key)

        if record is None:
            return False, "approval pending", None

        if record.status == "approved":
            return True, None, record

        if record.status == "sent":
            return False, "already sent", record

        if record.status == "rejected":
            return False, "rejected", record

        return False, record.reason or "approval pending", record

    def list_pending(self, tenant_id: str) -> list[ApprovalRecord]:
        return [
            record
            for record in self._load_tenant(tenant_id).values()
            if record.status == "pending"
        ]

    def all_records(self, tenant_id: str) -> Iterable[ApprovalRecord]:
        return self._load_tenant(tenant_id).values()

    def get_by_notice(self, tenant_id: str, notice_id: str) -> ApprovalRecord | None:
        return self._get_optional_by_notice(tenant_id, notice_id)

    # Internal helpers -------------------------------------------------

    def _load_tenant(self, tenant_id: str) -> dict[str, ApprovalRecord]:
        if tenant_id in self._cache:
            return self._cache[tenant_id]

        tenant_dir = self.base_path / tenant_id / "audit"
        tenant_dir.mkdir(parents=True, exist_ok=True)
        path = tenant_dir / "approvals.json"

        if not path.exists():
            records: dict[str, ApprovalRecord] = {}
        else:
            with path.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
            records = {
                key: ApprovalRecord.from_dict(value)
                for key, value in payload.get("records", {}).items()
            }

        self._cache[tenant_id] = records
        return records

    def _persist(self, tenant_id: str) -> None:
        records = self._cache.get(tenant_id, {})
        tenant_dir = self.base_path / tenant_id / "audit"
        tenant_dir.mkdir(parents=True, exist_ok=True)
        path = tenant_dir / "approvals.json"

        data = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "records": {key: record.to_dict() for key, record in records.items()},
        }

        with path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)

    def _get_required(self, tenant_id: str, notice_id: str, stage: DunningStage) -> ApprovalRecord:
        record = self._get_optional(tenant_id, notice_id, stage)
        if record is None:
            raise ValueError(f"No approval record for {tenant_id}:{notice_id}:{stage.value}")
        return record

    def _get_optional(self, tenant_id: str, notice_id: str, stage: DunningStage) -> ApprovalRecord | None:
        records = self._load_tenant(tenant_id)
        for record in records.values():
            if record.notice_id == notice_id and record.stage == stage:
                return record
        return None

    def _get_optional_by_notice(self, tenant_id: str, notice_id: str) -> ApprovalRecord | None:
        records = self._load_tenant(tenant_id)
        for record in records.values():
            if record.notice_id == notice_id:
                return record
        return None

    @staticmethod
    def _key(idempotency_key: str) -> str:
        return idempotency_key.lower()


