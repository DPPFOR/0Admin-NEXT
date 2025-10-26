"""Inbox parsed tables (parsed_items + chunks)

Revision ID: 20251019_inbox_parsed
Revises: 251018_schema_v1_inbox
Create Date: 2025-10-19 13:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20251019_inbox_parsed"
down_revision: Union[str, None] = "251018_schema_v1_inbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS inbox_parsed")

    op.create_table(
        "parsed_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),
        sa.Column("quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("amount", sa.Text(), nullable=True),
        sa.Column("invoice_no", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint("tenant_id", "content_hash", name="uq_parsed_items__tenant_hash"),
        schema="inbox_parsed",
    )

    op.create_index("ix_parsed_items_tenant", "parsed_items", ["tenant_id"], schema="inbox_parsed")

    op.create_table(
        "parsed_item_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parsed_item_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.ForeignKeyConstraint(["parsed_item_id"], ["inbox_parsed.parsed_items.id"], ondelete="CASCADE", name="fk_parsed_item_chunks__parsed_item"),
        sa.UniqueConstraint("parsed_item_id", "kind", "seq", name="uq_parsed_item_chunks__unique"),
        schema="inbox_parsed",
    )

    op.create_index("ix_parsed_item_chunks_parent", "parsed_item_chunks", ["parsed_item_id"], schema="inbox_parsed")


def downgrade() -> None:
    op.drop_index("ix_parsed_item_chunks_parent", table_name="parsed_item_chunks", schema="inbox_parsed")
    op.drop_table("parsed_item_chunks", schema="inbox_parsed")

    op.drop_index("ix_parsed_items_tenant", table_name="parsed_items", schema="inbox_parsed")
    op.drop_table("parsed_items", schema="inbox_parsed")

    op.execute("DROP SCHEMA IF EXISTS inbox_parsed CASCADE")
