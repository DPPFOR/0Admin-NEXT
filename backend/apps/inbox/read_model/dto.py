from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class InvoiceRowDTO:
    id: UUID
    tenant_id: UUID
    content_hash: str
    amount: Decimal | None
    invoice_no: str | None
    due_date: date | None
    quality_status: str
    confidence: float
    created_at: datetime
    flags: dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Decimal | None = None


@dataclass(frozen=True)
class PaymentRowDTO:
    id: UUID
    tenant_id: UUID
    content_hash: str
    amount: Decimal | None
    currency: str | None
    counterparty: str | None
    payment_date: date | None
    quality_status: str
    confidence: float
    created_at: datetime
    flags: dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Decimal | None = None


@dataclass(frozen=True)
class NeedsReviewRowDTO:
    id: UUID
    tenant_id: UUID
    doc_type: str
    quality_status: str
    confidence: float
    created_at: datetime
    content_hash: str
    flags: dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Decimal | None = None


@dataclass(frozen=True)
class TenantSummaryDTO:
    tenant_id: UUID
    cnt_items: int
    cnt_invoices: int
    cnt_payments: int
    cnt_other: int
    cnt_needing_review: int
    cnt_mvr_preview: int = 0
    avg_confidence: float | None = None
    avg_mvr_score: float | None = None
