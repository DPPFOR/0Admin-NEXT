from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
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


@dataclass(frozen=True)
class NeedsReviewRowDTO:
    id: UUID
    tenant_id: UUID
    doc_type: str
    quality_status: str
    confidence: float
    created_at: datetime
    content_hash: str


@dataclass(frozen=True)
class TenantSummaryDTO:
    tenant_id: UUID
    cnt_items: int
    cnt_invoices: int
    cnt_needing_review: int
    avg_confidence: Optional[float]
