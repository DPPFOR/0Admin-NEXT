from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from backend.apps.inbox.read_model.query import (
    fetch_invoices_latest,
    fetch_items_needing_review,
    fetch_tenant_summary,
)


RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL")


def _ensure_database_ready() -> None:
    cfg = Config("alembic.ini")
    if DB_URL:
        cfg.set_main_option("sqlalchemy.url", DB_URL)
    command.upgrade(cfg, "head")


def _seed_data(engine):
    now = datetime.utcnow()
    tenant = "00000000-0000-0000-0000-000000000001"
    invoice_content = "invoice-hash"
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS inbox_parsed"))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_item_chunks CASCADE"))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_items CASCADE"))

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items (
                    id, tenant_id, content_hash, doc_type, quality_flags, payload,
                    amount, invoice_no, due_date,
                    created_at, updated_at, doctype, quality_status, confidence, rules
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'invoice', '[]'::jsonb, '{}'::jsonb,
                    :amount, :invoice_no, :due_date,
                    :created_at, :updated_at, 'invoice', 'accepted', :confidence, '[]'::jsonb
                )
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant,
                "content_hash": invoice_content,
                "amount": Decimal("199.90"),
                "invoice_no": "INV-2025-0001",
                "due_date": now.date(),
                "created_at": now - timedelta(minutes=10),
                "updated_at": now - timedelta(minutes=5),
                "confidence": Decimal("90.00"),
            },
        )

        latest_invoice_id = str(uuid4())
        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items (
                    id, tenant_id, content_hash, doc_type, quality_flags, payload,
                    amount, invoice_no, due_date,
                    created_at, updated_at, doctype, quality_status, confidence, rules
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'invoice', '[]'::jsonb, '{}'::jsonb,
                    :amount, :invoice_no, :due_date,
                    :created_at, :updated_at, 'invoice', 'accepted', :confidence, '[]'::jsonb
                )
                """
            ),
            {
                "id": latest_invoice_id,
                "tenant_id": tenant,
                "content_hash": invoice_content,
                "amount": Decimal("250.00"),
                "invoice_no": "INV-2025-0002",
                "due_date": now.date(),
                "created_at": now - timedelta(minutes=2),
                "updated_at": now - timedelta(minutes=1),
                "confidence": Decimal("95.00"),
            },
        )

        review_id = str(uuid4())
        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items (
                    id, tenant_id, content_hash, doc_type, quality_flags, payload,
                    amount, invoice_no, due_date,
                    created_at, updated_at, doctype, quality_status, confidence, rules
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'pdf', '[]'::jsonb, '{}'::jsonb,
                    NULL, NULL, NULL,
                    :created_at, :updated_at, 'unknown', 'needs_review', :confidence, '[]'::jsonb
                )
                """
            ),
            {
                "id": review_id,
                "tenant_id": tenant,
                "content_hash": "review-hash",
                "created_at": now - timedelta(minutes=4),
                "updated_at": now - timedelta(minutes=3),
                "confidence": Decimal("40.00"),
            },
        )

    return {
        "tenant": tenant,
        "latest_invoice_id": latest_invoice_id,
        "review_id": review_id,
    }


@pytest.mark.skipif(not RUN_DB_TESTS or not DB_URL, reason="requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL")
def test_read_model_queries():
    _ensure_database_ready()
    engine = create_engine(DB_URL, future=True)
    ids = _seed_data(engine)

    invoices = fetch_invoices_latest(ids["tenant"])
    assert len(invoices) == 1
    assert str(invoices[0].id) == ids["latest_invoice_id"]
    assert invoices[0].invoice_no == "INV-2025-0002"

    review_items = fetch_items_needing_review(ids["tenant"])
    assert len(review_items) == 1
    assert str(review_items[0].id) == ids["review_id"]
    assert review_items[0].quality_status == "needs_review"

    summary = fetch_tenant_summary(ids["tenant"])
    assert summary is not None
    assert summary.cnt_items == 3
    assert summary.cnt_invoices == 2
    assert summary.cnt_needing_review == 1
    assert summary.avg_confidence is not None
