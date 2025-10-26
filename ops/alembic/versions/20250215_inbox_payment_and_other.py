"""Extend parsed items with payment/other support and refresh read-model views.

Revision ID: 20250215_inbox_payment_and_other
Revises: 20250214_outbox_events
Create Date: 2025-02-15 09:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20250215_inbox_payment_and_other"
down_revision: Union[str, None] = "20250214_outbox_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "inbox_parsed"
TABLE = "parsed_items"

VIEW_INVOICES_LATEST = f"{SCHEMA}.v_invoices_latest"
VIEW_PAYMENTS_LATEST = f"{SCHEMA}.v_payments_latest"
VIEW_ITEMS_REVIEW = f"{SCHEMA}.v_items_needing_review"
VIEW_TENANT_SUMMARY = f"{SCHEMA}.v_inbox_by_tenant"


def _ensure_columns() -> None:
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ADD COLUMN IF NOT EXISTS doctype TEXT;
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ADD COLUMN IF NOT EXISTS quality_status TEXT;
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ADD COLUMN IF NOT EXISTS confidence NUMERIC(5, 2);
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ADD COLUMN IF NOT EXISTS rules JSONB;
        """
    )

    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ALTER COLUMN doctype SET DEFAULT 'invoice';
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ALTER COLUMN quality_status SET DEFAULT 'needs_review';
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ALTER COLUMN confidence SET DEFAULT 0;
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ALTER COLUMN rules SET DEFAULT '[]'::jsonb;
        """
    )

    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
           SET doctype = COALESCE(NULLIF(doctype, ''), 'invoice'),
               quality_status = COALESCE(NULLIF(quality_status, ''), 'needs_review'),
               confidence = COALESCE(confidence, 0),
               rules = COALESCE(rules, '[]'::jsonb)
         WHERE doctype IS NULL
            OR doctype = ''
            OR quality_status IS NULL
            OR quality_status = ''
            OR confidence IS NULL
            OR rules IS NULL;
        """
    )


def _create_views() -> None:
    for view in (VIEW_PAYMENTS_LATEST, VIEW_ITEMS_REVIEW, VIEW_INVOICES_LATEST, VIEW_TENANT_SUMMARY):
        op.execute(f"DROP VIEW IF EXISTS {view}")

    op.execute(
        f"""
        CREATE OR REPLACE VIEW {VIEW_INVOICES_LATEST} AS
        SELECT id,
               tenant_id,
               content_hash,
               doctype,
               quality_status,
               confidence,
               amount,
               invoice_no,
               due_date,
               created_at
        FROM (
            SELECT pi.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, content_hash
                       ORDER BY updated_at DESC
                   ) AS rn
            FROM {SCHEMA}.{TABLE} AS pi
            WHERE pi.doctype = 'invoice'
        ) sub
        WHERE sub.rn = 1;
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE VIEW {VIEW_PAYMENTS_LATEST} AS
        SELECT id,
               tenant_id,
               content_hash,
               doctype,
               quality_status,
               confidence,
               amount,
               (payload -> 'extracted' -> 'payment' ->> 'currency') AS currency,
               (payload -> 'extracted' -> 'payment' ->> 'counterparty') AS counterparty,
               NULLIF(payload -> 'extracted' -> 'payment' ->> 'payment_date', '')::date AS payment_date,
               created_at
        FROM (
            SELECT pi.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, content_hash
                       ORDER BY updated_at DESC
                   ) AS rn
            FROM {SCHEMA}.{TABLE} AS pi
            WHERE pi.doctype = 'payment'
        ) sub
        WHERE sub.rn = 1;
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE VIEW {VIEW_ITEMS_REVIEW} AS
        SELECT id,
               tenant_id,
               doctype,
               quality_status,
               confidence,
               created_at,
               content_hash
        FROM {SCHEMA}.{TABLE}
        WHERE quality_status IN ('needs_review', 'rejected');
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE VIEW {VIEW_TENANT_SUMMARY} AS
        SELECT
            tenant_id,
            COUNT(*) AS cnt_items,
            COUNT(*) FILTER (WHERE doctype = 'invoice') AS cnt_invoices,
            COUNT(*) FILTER (WHERE doctype = 'payment') AS cnt_payments,
            COUNT(*) FILTER (WHERE doctype = 'other') AS cnt_other,
            COUNT(*) FILTER (WHERE quality_status IN ('needs_review', 'rejected')) AS cnt_needing_review,
            AVG(confidence) AS avg_confidence
        FROM {SCHEMA}.{TABLE}
        GROUP BY tenant_id;
        """
    )


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    _ensure_columns()
    _create_views()


def downgrade() -> None:
    op.execute(f"DROP VIEW IF EXISTS {VIEW_PAYMENTS_LATEST}")

    op.execute(
        f"""
        CREATE OR REPLACE VIEW {VIEW_INVOICES_LATEST} AS
        SELECT id,
               tenant_id,
               content_hash,
               doc_type,
               quality_status,
               confidence,
               amount,
               invoice_no,
               due_date,
               created_at
        FROM (
            SELECT pi.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, content_hash
                       ORDER BY updated_at DESC
                   ) AS rn
            FROM {SCHEMA}.{TABLE} AS pi
            WHERE pi.doc_type = 'invoice'
        ) sub
        WHERE sub.rn = 1;
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE VIEW {VIEW_ITEMS_REVIEW} AS
        SELECT id,
               tenant_id,
               doc_type,
               quality_status,
               confidence,
               created_at,
               content_hash
        FROM {SCHEMA}.{TABLE}
        WHERE quality_status IN ('needs_review', 'rejected');
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE VIEW {VIEW_TENANT_SUMMARY} AS
        SELECT
            tenant_id,
            COUNT(*) AS cnt_items,
            COUNT(*) FILTER (WHERE doc_type = 'invoice') AS cnt_invoices,
            COUNT(*) FILTER (WHERE quality_status IN ('needs_review', 'rejected')) AS cnt_needing_review,
            AVG(confidence) AS avg_confidence
        FROM {SCHEMA}.{TABLE}
        GROUP BY tenant_id;
        """
    )
