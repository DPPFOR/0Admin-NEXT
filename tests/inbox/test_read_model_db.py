from __future__ import annotations

import json
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
    fetch_payments_latest,
    fetch_tenant_summary,
)

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL")

TENANT_ID = "00000000-0000-0000-0000-000000000001"


def _ensure_database_ready(engine) -> None:
    """Self-heal schema/tables/indexes and ensure migrations (views) are in place."""
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS inbox_parsed"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS inbox_parsed.parsed_items (
                    id UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    content_hash TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    doctype TEXT NOT NULL DEFAULT 'unknown',
                    quality_status TEXT NOT NULL DEFAULT 'needs_review',
                    confidence NUMERIC(5,2) NOT NULL DEFAULT 0,
                    amount NUMERIC(18,2),
                    invoice_no TEXT,
                    due_date DATE,
                    quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    rules JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
                    UNIQUE (tenant_id, content_hash)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS inbox_parsed.parsed_item_chunks (
                    id UUID PRIMARY KEY,
                    parsed_item_id UUID NOT NULL,
                    seq INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_item_kind_seq
                ON inbox_parsed.parsed_item_chunks(parsed_item_id, kind, seq)
                """
            )
        )

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "ops/alembic")
    if DB_URL:
        cfg.set_main_option("sqlalchemy.url", DB_URL)
    elif engine:
        cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "head")


def _reset_tenant(engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM inbox_parsed.parsed_item_chunks
                WHERE parsed_item_id IN (
                    SELECT id FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id
                )
                """
            ),
            {"tenant_id": tenant_id},
        )
        conn.execute(
            text("DELETE FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )


def _seed_data(engine):
    base_time = datetime(2025, 1, 1, 12, 0, 0)

    accepted_invoice_id = str(uuid4())
    review_invoice_id = str(uuid4())
    payment_id = str(uuid4())
    other_id = str(uuid4())

    _reset_tenant(engine, TENANT_ID)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items AS pi (
                    id, tenant_id, content_hash, doc_type, doctype, quality_status, confidence,
                    amount, invoice_no, due_date, quality_flags, payload, rules,
                    flags, mvr_preview, mvr_score,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'invoice', 'invoice', 'accepted', :confidence,
                    :amount, :invoice_no, :due_date, '[]'::jsonb, '{}'::jsonb, '[]'::jsonb,
                    '{}'::jsonb, false, NULL,
                    :created_at, :updated_at
                )
                ON CONFLICT (tenant_id, content_hash)
                DO UPDATE SET
                    id = EXCLUDED.id,
                    doc_type = EXCLUDED.doc_type,
                    doctype = EXCLUDED.doctype,
                    quality_status = EXCLUDED.quality_status,
                    confidence = EXCLUDED.confidence,
                    amount = EXCLUDED.amount,
                    invoice_no = EXCLUDED.invoice_no,
                    due_date = EXCLUDED.due_date,
                    payload = EXCLUDED.payload,
                    rules = EXCLUDED.rules,
                    flags = EXCLUDED.flags,
                    mvr_preview = EXCLUDED.mvr_preview,
                    mvr_score = EXCLUDED.mvr_score,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "id": accepted_invoice_id,
                "tenant_id": TENANT_ID,
                "content_hash": "invoice-hash-accepted",
                "confidence": Decimal("95.00"),
                "amount": Decimal("250.00"),
                "invoice_no": "INV-2025-0001",
                "due_date": base_time.date(),
                "created_at": base_time,
                "updated_at": base_time + timedelta(minutes=1),
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items AS pi (
                    id, tenant_id, content_hash, doc_type, doctype, quality_status, confidence,
                    amount, invoice_no, due_date, quality_flags, payload, rules,
                    flags, mvr_preview, mvr_score,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'invoice', 'invoice', 'needs_review', :confidence,
                    NULL, NULL, NULL, '[]'::jsonb, '{}'::jsonb, '[]'::jsonb,
                    '{}'::jsonb, false, NULL,
                    :created_at, :updated_at
                )
                ON CONFLICT (tenant_id, content_hash)
                DO UPDATE SET
                    id = EXCLUDED.id,
                    doc_type = EXCLUDED.doc_type,
                    doctype = EXCLUDED.doctype,
                    quality_status = EXCLUDED.quality_status,
                    confidence = EXCLUDED.confidence,
                    amount = EXCLUDED.amount,
                    invoice_no = EXCLUDED.invoice_no,
                    due_date = EXCLUDED.due_date,
                    payload = EXCLUDED.payload,
                    rules = EXCLUDED.rules,
                    flags = EXCLUDED.flags,
                    mvr_preview = EXCLUDED.mvr_preview,
                    mvr_score = EXCLUDED.mvr_score,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "id": review_invoice_id,
                "tenant_id": TENANT_ID,
                "content_hash": "invoice-hash-review",
                "confidence": Decimal("45.00"),
                "created_at": base_time - timedelta(minutes=5),
                "updated_at": base_time - timedelta(minutes=4),
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_item_chunks AS c (
                    id, parsed_item_id, seq, kind, payload, created_at
                ) VALUES (
                    :id, :parsed_item_id, :seq, :kind, (:payload)::jsonb, :created_at
                )
                ON CONFLICT (parsed_item_id, kind, seq)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    created_at = EXCLUDED.created_at
                """
            ),
            {
                "id": str(uuid4()),
                "parsed_item_id": accepted_invoice_id,
                "seq": 1,
                "kind": "table",
                "payload": json.dumps(
                    {"headers": ["item", "price"], "rows": [["Consulting", "250.00"]]}
                ),
                "created_at": base_time,
            },
        )

        payment_payload = json.dumps(
            {
                "extracted": {
                    "payment": {
                        "amount": "250.00",
                        "currency": "EUR",
                        "payment_date": base_time.date().isoformat(),
                        "counterparty": "ACME Bank",
                    }
                }
            }
        )

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items (
                    id, tenant_id, content_hash, doc_type, doctype, quality_status, confidence,
                    amount, invoice_no, due_date, quality_flags, payload, rules,
                    flags, mvr_preview, mvr_score,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'payment', 'payment', 'accepted', :confidence,
                    :amount, NULL, :payment_date, '[]'::jsonb, (:payload)::jsonb, '[]'::jsonb,
                    (:flags)::jsonb, true, :mvr_score,
                    :created_at, :updated_at
                )
                ON CONFLICT (tenant_id, content_hash)
                DO NOTHING
                """
            ),
            {
                "id": payment_id,
                "tenant_id": TENANT_ID,
                "content_hash": "payment-good-0001",
                "confidence": Decimal("100.00"),
                "amount": Decimal("250.00"),
                "payment_date": base_time.date(),
                "payload": payment_payload,
                "flags": json.dumps({"mvr_preview": True, "enable_table_boost": True}),
                "mvr_score": Decimal("0.00"),
                "created_at": base_time + timedelta(minutes=2),
                "updated_at": base_time + timedelta(minutes=2),
            },
        )

        other_payload = json.dumps(
            {
                "extracted": {
                    "kv": [
                        {"key": "Subject", "value": "General correspondence"},
                        {"key": "Reference", "value": "REF-2025-02"},
                    ]
                }
            }
        )

        conn.execute(
            text(
                """
                INSERT INTO inbox_parsed.parsed_items (
                    id, tenant_id, content_hash, doc_type, doctype, quality_status, confidence,
                    amount, invoice_no, due_date, quality_flags, payload, rules,
                    flags, mvr_preview, mvr_score,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :content_hash, 'other', 'other', 'needs_review', :confidence,
                    NULL, NULL, NULL, '[]'::jsonb, (:payload)::jsonb, '[]'::jsonb,
                    (:flags)::jsonb, false, NULL,
                    :created_at, :updated_at
                )
                ON CONFLICT (tenant_id, content_hash)
                DO NOTHING
                """
            ),
            {
                "id": other_id,
                "tenant_id": TENANT_ID,
                "content_hash": "other-min-0001",
                "confidence": Decimal("58.00"),
                "payload": other_payload,
                "flags": json.dumps({"enable_table_boost": False}),
                "created_at": base_time - timedelta(minutes=2),
                "updated_at": base_time - timedelta(minutes=2),
            },
        )

    return {
        "accepted_invoice_id": accepted_invoice_id,
        "review_invoice_id": review_invoice_id,
        "payment_id": payment_id,
        "other_id": other_id,
        "tenant": TENANT_ID,
    }


@pytest.mark.skipif(
    not RUN_DB_TESTS or not DB_URL, reason="requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL"
)
def test_read_model_queries():
    engine = create_engine(DB_URL, future=True)
    _ensure_database_ready(engine)
    ids = _seed_data(engine)

    invoices = fetch_invoices_latest(ids["tenant"])
    assert len(invoices) >= 1
    first_invoice = invoices[0]
    assert str(first_invoice.id) == ids["accepted_invoice_id"]
    assert first_invoice.invoice_no == "INV-2025-0001"
    assert first_invoice.quality_status == "accepted"
    assert first_invoice.amount == Decimal("250.00")
    assert first_invoice.confidence == 95.0

    review_items = fetch_items_needing_review(ids["tenant"])
    assert review_items, "expected at least one item needing review"
    review_ids = {str(item.id): item for item in review_items}
    assert ids["review_invoice_id"] in review_ids
    assert review_ids[ids["review_invoice_id"]].quality_status == "needs_review"
    assert any(item.doc_type == "other" for item in review_items)

    payments = fetch_payments_latest(ids["tenant"])
    assert payments, "expected payment projection"
    payment = next(item for item in payments if str(item.id) == ids["payment_id"])
    assert payment.counterparty == "ACME Bank"
    assert payment.currency == "EUR"
    assert payment.quality_status == "accepted"
    assert payment.flags.get("mvr_preview") is True
    assert payment.mvr_preview is True
    assert payment.mvr_score == Decimal("0.00")

    summary = fetch_tenant_summary(ids["tenant"])
    assert summary is not None
    assert summary.cnt_items == 4
    assert summary.cnt_invoices == 2
    assert summary.cnt_payments == 1
    assert summary.cnt_other == 1
    assert summary.cnt_needing_review == 2
    expected_avg = (95.0 + 45.0 + 100.0 + 58.0) / 4
    assert summary.avg_confidence == pytest.approx(expected_avg, rel=1e-3)
    assert summary.cnt_mvr_preview == 1
    assert summary.avg_mvr_score == pytest.approx(0.0, rel=1e-3)
