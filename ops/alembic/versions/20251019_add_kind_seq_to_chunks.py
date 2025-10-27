"""Add kind/seq columns and unique index on parsed_item_chunks

Revision ID: 20251019_add_kind_seq_to_chunks
Revises: 20251019_inbox_parsed
Create Date: 2025-10-19 13:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20251019_add_kind_seq_to_chunks"
down_revision: str | None = "20251019_inbox_parsed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "inbox_parsed"
PARSED_ITEMS = "parsed_items"
CHUNKS = "parsed_item_chunks"
INDEX_NAME = "idx_chunks_item_kind_seq"


def _ensure_schema() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")


def _ensure_parsed_items() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if PARSED_ITEMS not in inspector.get_table_names(schema=SCHEMA):
        op.create_table(
            PARSED_ITEMS,
            sa.Column(
                "id",
                sa.dialects.postgresql.UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
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
            sa.Column("amount", sa.Text(), nullable=True),
            sa.Column("invoice_no", sa.Text(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
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
        op.create_index(
            "ix_parsed_items_tenant",
            PARSED_ITEMS,
            ["tenant_id"],
            schema=SCHEMA,
        )


def _ensure_chunks() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if CHUNKS not in inspector.get_table_names(schema=SCHEMA):
        op.create_table(
            CHUNKS,
            sa.Column(
                "id",
                sa.dialects.postgresql.UUID(as_uuid=False),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("parsed_item_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=True),
            sa.Column("kind", sa.Text(), nullable=True),
            sa.Column(
                "payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False
            ),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("timezone('utc', now())"),
            ),
            sa.ForeignKeyConstraint(
                ["parsed_item_id"],
                [f"{SCHEMA}.{PARSED_ITEMS}.id"],
                ondelete="CASCADE",
                name="fk_parsed_item_chunks__parsed_item",
            ),
            schema=SCHEMA,
        )

    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(CHUNKS, schema=SCHEMA)}
    if "kind" not in columns:
        op.add_column(CHUNKS, sa.Column("kind", sa.Text(), nullable=True), schema=SCHEMA)
    if "seq" not in columns:
        op.add_column(CHUNKS, sa.Column("seq", sa.Integer(), nullable=True), schema=SCHEMA)

    op.execute(f"UPDATE {SCHEMA}.{CHUNKS} SET kind='table' WHERE kind IS NULL")
    op.execute(f"UPDATE {SCHEMA}.{CHUNKS} SET seq=1 WHERE seq IS NULL")

    op.execute(f"ALTER TABLE {SCHEMA}.{CHUNKS} ALTER COLUMN kind SET NOT NULL")
    op.execute(f"ALTER TABLE {SCHEMA}.{CHUNKS} ALTER COLUMN seq SET NOT NULL")

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(CHUNKS, schema=SCHEMA)}
    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name=CHUNKS, schema=SCHEMA)
    op.create_index(
        INDEX_NAME,
        CHUNKS,
        ["parsed_item_id", "kind", "seq"],
        unique=True,
        schema=SCHEMA,
    )


def upgrade() -> None:
    _ensure_schema()
    _ensure_parsed_items()
    _ensure_chunks()


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=CHUNKS, schema=SCHEMA, if_exists=True)
    op.execute(f"ALTER TABLE {SCHEMA}.{CHUNKS} ALTER COLUMN kind DROP NOT NULL")
    op.execute(f"ALTER TABLE {SCHEMA}.{CHUNKS} ALTER COLUMN seq DROP NOT NULL")
