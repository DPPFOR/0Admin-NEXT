from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from backend.apps.inbox.read_model.dto import (
    InvoiceRowDTO,
    PaymentRowDTO,
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
    assert dto.flags == {}
    assert dto.mvr_preview is False
    assert dto.mvr_score is None


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
    assert dto.flags == {}


def test_payment_row_dto_construction():
    dto = PaymentRowDTO(
        id=uuid4(),
        tenant_id=uuid4(),
        content_hash="payment",
        amount=Decimal("250.00"),
        currency="EUR",
        counterparty="ACME Bank",
        payment_date=date.today(),
        quality_status="accepted",
        confidence=88.5,
        created_at=datetime.utcnow(),
    )
    assert dto.currency == "EUR"
    assert dto.quality_status == "accepted"
    assert dto.flags == {}
    assert dto.mvr_preview is False


def test_tenant_summary_dto_optional_avg():
    dto = TenantSummaryDTO(
        tenant_id=uuid4(),
        cnt_items=3,
        cnt_invoices=2,
        cnt_payments=1,
        cnt_other=0,
        cnt_needing_review=1,
        avg_confidence=None,
    )
    assert dto.cnt_items == 3
    assert dto.avg_confidence is None
    assert dto.cnt_mvr_preview == 0
    assert dto.avg_mvr_score is None
