from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from backend.apps.inbox.read_model.dto import (
    InvoiceRowDTO,
    NeedsReviewRowDTO,
    TenantSummaryDTO,
)


def test_invoice_row_dto_construction():
    dto = InvoiceRowDTO(
        id=uuid4(),
        tenant_id=uuid4(),
        content_hash="abc",
        amount=Decimal("10.50"),
        invoice_no="INV-123",
        due_date=date.today(),
        quality_status="accepted",
        confidence=95.0,
        created_at=datetime.utcnow(),
    )
    assert dto.quality_status == "accepted"
    assert isinstance(dto.amount, Decimal)


def test_needs_review_row_dto_construction():
    dto = NeedsReviewRowDTO(
        id=uuid4(),
        tenant_id=uuid4(),
        doc_type="invoice",
        quality_status="needs_review",
        confidence=40.0,
        created_at=datetime.utcnow(),
        content_hash="hash",
    )
    assert dto.doc_type == "invoice"
    assert dto.confidence == 40.0


def test_tenant_summary_dto_optional_avg():
    dto = TenantSummaryDTO(
        tenant_id=uuid4(),
        cnt_items=3,
        cnt_invoices=2,
        cnt_needing_review=1,
        avg_confidence=None,
    )
    assert dto.cnt_items == 3
    assert dto.avg_confidence is None
