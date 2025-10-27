from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


def _ensure_mapping(payload: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{context} expected mapping payload, got {type(payload).__name__}")
    return payload


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


@dataclass
class InvoiceDTO:
    id: str
    tenant_id: str
    content_hash: str
    amount: float | None
    invoice_no: str | None
    due_date: str | None
    quality_status: str | None
    confidence: float | None
    created_at: str | None
    flags: dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: float | None = None

    @classmethod
    def from_json(cls, payload: Any) -> InvoiceDTO:
        data = _ensure_mapping(payload, "InvoiceDTO")
        return cls(
            id=str(data.get("id", "")),
            tenant_id=str(data.get("tenant_id", "")),
            content_hash=str(data.get("content_hash", "")),
            amount=data.get("amount"),
            invoice_no=data.get("invoice_no"),
            due_date=data.get("due_date"),
            quality_status=data.get("quality_status"),
            confidence=data.get("confidence"),
            created_at=data.get("created_at"),
            flags=_ensure_dict(data.get("flags")),
            mvr_preview=bool(data.get("mvr_preview", False)),
            mvr_score=data.get("mvr_score"),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaymentDTO:
    id: str
    tenant_id: str
    content_hash: str
    amount: float | None
    currency: str | None
    counterparty: str | None
    payment_date: str | None
    quality_status: str | None
    confidence: float | None
    created_at: str | None
    flags: dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: float | None = None

    @classmethod
    def from_json(cls, payload: Any) -> PaymentDTO:
        data = _ensure_mapping(payload, "PaymentDTO")
        return cls(
            id=str(data.get("id", "")),
            tenant_id=str(data.get("tenant_id", "")),
            content_hash=str(data.get("content_hash", "")),
            amount=data.get("amount"),
            currency=data.get("currency"),
            counterparty=data.get("counterparty"),
            payment_date=data.get("payment_date"),
            quality_status=data.get("quality_status"),
            confidence=data.get("confidence"),
            created_at=data.get("created_at"),
            flags=_ensure_dict(data.get("flags")),
            mvr_preview=bool(data.get("mvr_preview", False)),
            mvr_score=data.get("mvr_score"),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewItemDTO:
    id: str
    tenant_id: str
    doc_type: str | None
    quality_status: str | None
    confidence: float | None
    created_at: str | None
    content_hash: str | None
    flags: dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: float | None = None

    @classmethod
    def from_json(cls, payload: Any) -> ReviewItemDTO:
        data = _ensure_mapping(payload, "ReviewItemDTO")
        return cls(
            id=str(data.get("id", "")),
            tenant_id=str(data.get("tenant_id", "")),
            doc_type=data.get("doc_type"),
            quality_status=data.get("quality_status"),
            confidence=data.get("confidence"),
            created_at=data.get("created_at"),
            content_hash=data.get("content_hash"),
            flags=_ensure_dict(data.get("flags")),
            mvr_preview=bool(data.get("mvr_preview", False)),
            mvr_score=data.get("mvr_score"),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SummaryDTO:
    tenant_id: str
    cnt_items: int = 0
    cnt_invoices: int = 0
    cnt_payments: int = 0
    cnt_other: int = 0
    cnt_needing_review: int = 0
    cnt_mvr_preview: int = 0
    avg_confidence: float | None = None
    avg_mvr_score: float | None = None

    @classmethod
    def from_json(cls, payload: Any) -> SummaryDTO:
        data = _ensure_mapping(payload, "SummaryDTO")
        return cls(
            tenant_id=str(data.get("tenant_id", "")),
            cnt_items=int(data.get("cnt_items", 0) or 0),
            cnt_invoices=int(data.get("cnt_invoices", 0) or 0),
            cnt_payments=int(data.get("cnt_payments", 0) or 0),
            cnt_other=int(data.get("cnt_other", 0) or 0),
            cnt_needing_review=int(data.get("cnt_needing_review", 0) or 0),
            cnt_mvr_preview=int(data.get("cnt_mvr_preview", 0) or 0),
            avg_confidence=data.get("avg_confidence"),
            avg_mvr_score=data.get("avg_mvr_score"),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
