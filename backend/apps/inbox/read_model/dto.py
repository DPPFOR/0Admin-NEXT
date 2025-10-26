from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any
from uuid import UUID


@dataclass(frozen=True)
class InvoiceRowDTO:
    id: UUID
    tenant_id: UUID
    content_hash: str
    amount: Optional[Decimal]
    invoice_no: Optional[str]
    due_date: Optional[date]
    quality_status: str
    confidence: float
    created_at: datetime
    flags: Dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Optional[Decimal] = None


@dataclass(frozen=True)
class PaymentRowDTO:
    id: UUID
    tenant_id: UUID
    content_hash: str
    amount: Optional[Decimal]
    currency: Optional[str]
    counterparty: Optional[str]
    payment_date: Optional[date]
    quality_status: str
    confidence: float
    created_at: datetime
    flags: Dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Optional[Decimal] = None


@dataclass(frozen=True)
class NeedsReviewRowDTO:
    id: UUID
    tenant_id: UUID
    doc_type: str
    quality_status: str
    confidence: float
    created_at: datetime
    content_hash: str
    flags: Dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Optional[Decimal] = None


@dataclass(frozen=True)
class TenantSummaryDTO:
    tenant_id: UUID
    cnt_items: int
    cnt_invoices: int
    cnt_payments: int
    cnt_other: int
    cnt_needing_review: int
    cnt_mvr_preview: int = 0
    avg_confidence: Optional[float] = None
    avg_mvr_score: Optional[float] = None
