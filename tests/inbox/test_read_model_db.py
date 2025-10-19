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
    tenant = "00000000-0000-0000-0000-000000000001"
    base_time = datetime(2025, 1, 1, 12, 0, 0)
    first_invoice_id = str(uuid4())
    latest_invoice_id = str(uuid4())
    review_id = str(uuid4())
    first_invoice_hash = "invoice-hash-v1"
    latest_invoice_hash = "invoice-hash-v2"
    review_hash = "review-hash"

    tenant = "00000000-0000-0000-0000-000000000001"
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS inbox_parsed"))
        conn.execute(
            text(
                "DELETE FROM inbox_parsed.parsed_item_chunks "
                "WHERE parsed_item_id IN (SELECT id FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant)"
            ),
            {"tenant": tenant},
        )
        conn.execute(
            text("DELETE FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant"),
            {"tenant": tenant},
        )

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items AS pi (
                    id, tenant_id, content_hash, doc_type, quality_flags, payload,
                    amount, invoice_no, due_date,
                    created_at, updated_at, doctype, quality_status, confidence, rules
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'invoice', '[]'::jsonb, '{}'::jsonb,
                    :amount, :invoice_no, :due_date,
                    :created_at, :updated_at, 'invoice', 'accepted', :confidence, '[]'::jsonb
                )
                ON CONFLICT (tenant_id, content_hash)
                DO UPDATE SET
                    id = EXCLUDED.id,
                    doc_type = EXCLUDED.doc_type,
                    quality_flags = EXCLUDED.quality_flags,
                    payload = EXCLUDED.payload,
                    amount = EXCLUDED.amount,
                    invoice_no = EXCLUDED.invoice_no,
                    due_date = EXCLUDED.due_date,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    doctype = EXCLUDED.doctype,
                    quality_status = EXCLUDED.quality_status,
                    confidence = EXCLUDED.confidence,
                    rules = EXCLUDED.rules
                """
            ),
            {
                "id": first_invoice_id,
                "tenant_id": tenant,
                "content_hash": first_invoice_hash,
                "amount": Decimal("199.90"),
                "invoice_no": "INV-2025-0001",
                "due_date": base_time.date(),
                "created_at": base_time - timedelta(minutes=10),
                "updated_at": base_time - timedelta(minutes=5),
                "confidence": Decimal("90.00"),
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items AS pi (
                    id, tenant_id, content_hash, doc_type, quality_flags, payload,
                    amount, invoice_no, due_date,
                    created_at, updated_at, doctype, quality_status, confidence, rules
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'invoice', '[]'::jsonb, '{}'::jsonb,
                    :amount, :invoice_no, :due_date,
                    :created_at, :updated_at, 'invoice', 'accepted', :confidence, '[]'::jsonb
                )
                ON CONFLICT (tenant_id, content_hash)
                DO UPDATE SET
                    id = EXCLUDED.id,
                    doc_type = EXCLUDED.doc_type,
                    quality_flags = EXCLUDED.quality_flags,
                    payload = EXCLUDED.payload,
                    amount = EXCLUDED.amount,
                    invoice_no = EXCLUDED.invoice_no,
                    due_date = EXCLUDED.due_date,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    doctype = EXCLUDED.doctype,
                    quality_status = EXCLUDED.quality_status,
                    confidence = EXCLUDED.confidence,
                    rules = EXCLUDED.rules
                """
            ),
            {
                "id": latest_invoice_id,
                "tenant_id": tenant,
                "content_hash": latest_invoice_hash,
                "amount": Decimal("250.00"),
                "invoice_no": "INV-2025-0002",
                "due_date": base_time.date(),
                "created_at": base_time - timedelta(minutes=2),
                "updated_at": base_time - timedelta(minutes=1),
                "confidence": Decimal("95.00"),
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items AS pi (
                    id, tenant_id, content_hash, doc_type, quality_flags, payload,
                    amount, invoice_no, due_date,
                    created_at, updated_at, doctype, quality_status, confidence, rules
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'pdf', '[]'::jsonb, '{}'::jsonb,
                    NULL, NULL, NULL,
                    :created_at, :updated_at, 'unknown', 'needs_review', :confidence, '[]'::jsonb
                )
                ON CONFLICT (tenant_id, content_hash)
                DO UPDATE SET
                    id = EXCLUDED.id,
                    doc_type = EXCLUDED.doc_type,
                    quality_flags = EXCLUDED.quality_flags,
                    payload = EXCLUDED.payload,
                    amount = EXCLUDED.amount,
                    invoice_no = EXCLUDED.invoice_no,
                    due_date = EXCLUDED.due_date,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    doctype = EXCLUDED.doctype,
                    quality_status = EXCLUDED.quality_status,
                    confidence = EXCLUDED.confidence,
                    rules = EXCLUDED.rules
                """
            ),
            {
                "id": review_id,
                "tenant_id": tenant,
                "content_hash": review_hash,
                "created_at": base_time - timedelta(minutes=4),
                "updated_at": base_time - timedelta(minutes=3),
                "confidence": Decimal("40.00"),
            },
        )

    return {
        "tenant": tenant,
        "first_invoice_id": first_invoice_id,
        "latest_invoice_id": latest_invoice_id,
        "review_id": review_id,
    }


@pytest.mark.skipif(not RUN_DB_TESTS or not DB_URL, reason="requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL")
def test_read_model_queries():
    _ensure_database_ready()
    engine = create_engine(DB_URL, future=True)
    ids = _seed_data(engine)

    invoices = fetch_invoices_latest(ids["tenant"])
    assert len(invoices) == 2
    assert str(invoices[0].id) == ids["latest_invoice_id"]
    assert invoices[0].invoice_no == "INV-2025-0002"
    assert str(invoices[1].id) == ids["first_invoice_id"]

    review_items = fetch_items_needing_review(ids["tenant"])
    assert len(review_items) == 1
    assert str(review_items[0].id) == ids["review_id"]
    assert review_items[0].quality_status == "needs_review"

    summary = fetch_tenant_summary(ids["tenant"])
    assert summary is not None
    assert summary.cnt_items == 3
    assert summary.cnt_invoices == 2
    assert summary.cnt_needing_review == 1
    assert summary.avg_confidence == pytest.approx(75.0)
