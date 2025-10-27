"""Read model views for inbox parsed items.

Revision ID: 20251020_read_model_views
Revises: 20251019_invoice_quality_fields
Create Date: 2025-10-20 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20251020_read_model_views"
down_revision: str | None = "20251019_invoice_quality_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEMA = "inbox_parsed"
TABLE = "parsed_items"

IDX_TENANT_DOCTYPE = "idx_parsed_items_tenant_doctype"
IDX_QUALITY_STATUS = "idx_parsed_items_quality_status"
IDX_UPDATED_AT = "idx_parsed_items_updated_at_desc"

VIEW_INVOICES_LATEST = f"{SCHEMA}.v_invoices_latest"
VIEW_ITEMS_REVIEW = f"{SCHEMA}.v_items_needing_review"
VIEW_TENANT_SUMMARY = f"{SCHEMA}.v_inbox_by_tenant"


def _ensure_schema_exists() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")


def _create_indexes() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(TABLE, schema=SCHEMA)}

    if IDX_TENANT_DOCTYPE not in existing_indexes:
        op.create_index(
            IDX_TENANT_DOCTYPE,
            TABLE,
            ["tenant_id", "doc_type"],
            schema=SCHEMA,
        )

    if IDX_QUALITY_STATUS not in existing_indexes:
        op.create_index(
            IDX_QUALITY_STATUS,
            TABLE,
            ["quality_status"],
            schema=SCHEMA,
        )

    if IDX_UPDATED_AT not in existing_indexes:
        op.create_index(
            IDX_UPDATED_AT,
            TABLE,
            ["updated_at"],
            schema=SCHEMA,
            postgresql_using="btree",
        )


def _create_views() -> None:
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


def upgrade() -> None:
    _ensure_schema_exists()
    _create_indexes()
    _create_views()


def downgrade() -> None:
    for view in (VIEW_TENANT_SUMMARY, VIEW_ITEMS_REVIEW, VIEW_INVOICES_LATEST):
        op.execute(f"DROP VIEW IF EXISTS {view}")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(TABLE, schema=SCHEMA)}

    for idx_name in (IDX_UPDATED_AT, IDX_QUALITY_STATUS, IDX_TENANT_DOCTYPE):
        if idx_name in existing_indexes:
            op.drop_index(idx_name, table_name=TABLE, schema=SCHEMA)
