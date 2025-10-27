"""Add flags and MVR preview fields to parsed items and refresh views.

Revision ID: 20250216_flags_and_mvr_preview
Revises: 20250215_inbox_payment_and_other
Create Date: 2025-02-16 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20250216_flags_and_mvr_preview"
down_revision: str | None = "20250215_inbox_payment_and_other"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "inbox_parsed"
TABLE = "parsed_items"
INDEX_FLAGS = "idx_parsed_items_flags_gin"
VIEW_INVOICES_LATEST = f"{SCHEMA}.v_invoices_latest"
VIEW_PAYMENTS_LATEST = f"{SCHEMA}.v_payments_latest"
VIEW_ITEMS_REVIEW = f"{SCHEMA}.v_items_needing_review"
VIEW_TENANT_SUMMARY = f"{SCHEMA}.v_inbox_by_tenant"


def _ensure_columns() -> None:
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ADD COLUMN IF NOT EXISTS flags JSONB DEFAULT '{{}}'::jsonb;
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ADD COLUMN IF NOT EXISTS mvr_preview BOOLEAN DEFAULT false;
        """
    )
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.{TABLE}
            ADD COLUMN IF NOT EXISTS mvr_score NUMERIC(5, 2);
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
           SET flags = COALESCE(flags, '{{}}'::jsonb),
               mvr_preview = COALESCE(mvr_preview, false)
         WHERE flags IS NULL OR mvr_preview IS NULL;
        """
    )


def _rebuild_views() -> None:
    for view in (
        VIEW_TENANT_SUMMARY,
        VIEW_ITEMS_REVIEW,
        VIEW_PAYMENTS_LATEST,
        VIEW_INVOICES_LATEST,
    ):
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
               flags,
               mvr_preview,
               mvr_score,
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
               flags,
               mvr_preview,
               mvr_score,
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
               content_hash,
               flags,
               mvr_preview,
               mvr_score
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
            COUNT(*) FILTER (WHERE mvr_preview) AS cnt_mvr_preview,
            AVG(confidence) AS avg_confidence,
            AVG(mvr_score) AS avg_mvr_score
        FROM {SCHEMA}.{TABLE}
        GROUP BY tenant_id;
        """
    )


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    _ensure_columns()
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {INDEX_FLAGS}
        ON {SCHEMA}.{TABLE}
        USING GIN (flags)
        """
    )
    _rebuild_views()


def downgrade() -> None:
    for view in (
        VIEW_TENANT_SUMMARY,
        VIEW_ITEMS_REVIEW,
        VIEW_PAYMENTS_LATEST,
        VIEW_INVOICES_LATEST,
    ):
        op.execute(f"DROP VIEW IF EXISTS {view}")

    op.execute(f"DROP INDEX IF EXISTS {INDEX_FLAGS}")
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} DROP COLUMN IF EXISTS mvr_score")
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} DROP COLUMN IF EXISTS mvr_preview")
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} DROP COLUMN IF EXISTS flags")

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
