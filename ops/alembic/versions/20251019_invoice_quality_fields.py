"""Invoice quality fields for parsed_items.

Revision ID: 20251019_invoice_quality_fields
Revises: 20251019_add_kind_seq_to_chunks
Create Date: 2025-10-19 15:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20251019_invoice_quality_fields"
down_revision: str | None = "20251019_add_kind_seq_to_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "inbox_parsed"
TABLE = "parsed_items"
INDEX_NAME = "idx_parsed_items_tenant_qs"
QUALITY_CHECK_NAME = "ck_parsed_items_quality_status"
QUALITY_ALLOWED = ("accepted", "needs_review", "rejected")


def _ensure_schema_and_table() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names(schema=SCHEMA):
        op.create_table(
            TABLE,
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("content_hash", sa.Text(), nullable=False),
            sa.Column("doc_type", sa.Text(), nullable=False),
            sa.Column(
                "quality_flags",
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False
            ),
            sa.Column("amount", sa.Numeric(18, 2)),
            sa.Column("invoice_no", sa.Text()),
            sa.Column("due_date", sa.Date()),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("timezone('utc', now())"),
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("timezone('utc', now())"),
            ),
            sa.UniqueConstraint("tenant_id", "content_hash", name="uq_parsed_items__tenant_hash"),
            schema=SCHEMA,
        )


def _add_or_update_columns() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(TABLE, schema=SCHEMA)}

    if "doctype" not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                "doctype",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'unknown'"),
            ),
            schema=SCHEMA,
        )
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN doctype SET DEFAULT 'unknown'")
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN doctype SET NOT NULL")

    if "quality_status" not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                "quality_status",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'needs_review'"),
            ),
            schema=SCHEMA,
        )
    op.execute(
        f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN quality_status SET DEFAULT 'needs_review'"
    )
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN quality_status SET NOT NULL")

    existing_constraints = {
        constraint["name"] for constraint in inspector.get_check_constraints(TABLE, schema=SCHEMA)
    }
    if QUALITY_CHECK_NAME not in existing_constraints:
        allowed = ", ".join(f"'{value}'" for value in QUALITY_ALLOWED)
        op.execute(
            f"ALTER TABLE {SCHEMA}.{TABLE} "
            f"ADD CONSTRAINT {QUALITY_CHECK_NAME} "
            f"CHECK (quality_status IN ({allowed}))"
        )

    if "confidence" not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                "confidence",
                sa.Numeric(5, 2),
                nullable=False,
                server_default=sa.text("0"),
            ),
            schema=SCHEMA,
        )
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN confidence SET DEFAULT 0")
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN confidence SET NOT NULL")

    if "rules" not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                "rules",
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            schema=SCHEMA,
        )
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN rules SET DEFAULT '[]'::jsonb")
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} ALTER COLUMN rules SET NOT NULL")


def _create_index() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(TABLE, schema=SCHEMA)}
    if INDEX_NAME not in existing_indexes:
        op.create_index(
            INDEX_NAME,
            TABLE,
            ["tenant_id", "quality_status"],
            schema=SCHEMA,
        )


def upgrade() -> None:
    _ensure_schema_and_table()
    _add_or_update_columns()
    _create_index()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(TABLE, schema=SCHEMA)}
    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name=TABLE, schema=SCHEMA)
    op.execute(f"ALTER TABLE {SCHEMA}.{TABLE} DROP CONSTRAINT IF EXISTS {QUALITY_CHECK_NAME}")

    columns = {col["name"] for col in inspector.get_columns(TABLE, schema=SCHEMA)}

    for column in ("rules", "confidence", "quality_status", "doctype"):
        if column in columns:
            op.drop_column(TABLE, column, schema=SCHEMA)
        else:
            op.execute(
                sa.text(f"/* downgrade noop: column {column} missing on {SCHEMA}.{TABLE} */")
            )
