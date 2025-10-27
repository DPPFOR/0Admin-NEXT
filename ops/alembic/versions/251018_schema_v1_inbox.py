"""Schema v1 inbox - inbox_items, parsed_items, chunks, event_outbox, processed_events, dead_letters

Revision ID: 251018_schema_v1_inbox
Revises: 251018_initial_baseline
Create Date: 2025-10-18 17:45:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "251018_schema_v1_inbox"
down_revision = "251018_initial_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Schema v1 inbox - zero_admin tables for inbox processing pipeline"""

    # inbox_items table - tracks incoming documents
    op.create_table(
        "inbox_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_inbox_items"),
        sa.CheckConstraint(
            "status IN ('received','validated','parsed','error')",
            name="ck_inbox_items__status_valid",
        ),
        schema="zero_admin",
    )

    # parsed_items table - parsed content from inbox items
    op.create_table(
        "parsed_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("inbox_item_id", sa.UUID(), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parsed_items"),
        sa.ForeignKeyConstraint(
            ["inbox_item_id"],
            ["zero_admin.inbox_items.id"],
            name="fk_inbox_item_id_inbox_items",
            ondelete="CASCADE",
        ),
        schema="zero_admin",
    )

    # chunks table - text chunks from parsed documents
    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("parsed_item_id", sa.UUID(), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.ForeignKeyConstraint(
            ["parsed_item_id"],
            ["zero_admin.parsed_items.id"],
            name="fk_parsed_item_id_parsed_items",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "parsed_item_id", "seq_no", name="uq_chunks__seq"),
        schema="zero_admin",
    )

    # event_outbox table - outbound events for async processing
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_event_outbox"),
        sa.CheckConstraint(
            "status IN ('pending','processing','sent','failed','dlq')",
            name="ck_event_outbox__status_valid",
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", "event_type", name="uq_event_outbox__idem"
        ),
        schema="zero_admin",
    )

    # processed_events table - idempotency tracking for processed events
    op.create_table(
        "processed_events",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "processed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "event_type", "idempotency_key", name="pk_processed_events"
        ),
        schema="zero_admin",
    )

    # dead_letters table - failed event storage
    op.create_table(
        "dead_letters",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column(
            "failed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dead_letters"),
        schema="zero_admin",
    )

    # Additional unique constraint for inbox_items content_hash
    op.create_unique_constraint(
        "uq_inbox_items__content_hash",
        "inbox_items",
        ["tenant_id", "content_hash"],
        schema="zero_admin",
    )

    # Create indexes for query optimization
    op.create_index(
        "ix_inbox_items_created_at", "inbox_items", ["tenant_id", "created_at"], schema="zero_admin"
    )
    op.create_index(
        "ix_inbox_items_status", "inbox_items", ["tenant_id", "status"], schema="zero_admin"
    )
    op.create_index(
        "ix_parsed_items_created_at",
        "parsed_items",
        ["tenant_id", "created_at"],
        schema="zero_admin",
    )
    op.create_index(
        "ix_parsed_items_inbox_item_id",
        "parsed_items",
        ["tenant_id", "inbox_item_id"],
        schema="zero_admin",
    )
    op.create_index(
        "ix_chunks_parsed_item_id", "chunks", ["tenant_id", "parsed_item_id"], schema="zero_admin"
    )
    op.create_index("ix_chunks_seq_no", "chunks", ["tenant_id", "seq_no"], schema="zero_admin")
    op.create_index(
        "ix_event_outbox_created_at",
        "event_outbox",
        ["tenant_id", "created_at"],
        schema="zero_admin",
    )
    op.create_index(
        "ix_event_outbox_status", "event_outbox", ["tenant_id", "status"], schema="zero_admin"
    )

    # Create triggers for set_updated_at function (executed directly since function exists)
    op.execute(
        """
        CREATE TRIGGER trg_inbox_items_set_updated_at
            BEFORE UPDATE ON zero_admin.inbox_items
            FOR EACH ROW EXECUTE FUNCTION zero_admin.set_updated_at();
    """
    )

    op.execute(
        """
        CREATE TRIGGER trg_parsed_items_set_updated_at
            BEFORE UPDATE ON zero_admin.parsed_items
            FOR EACH ROW EXECUTE FUNCTION zero_admin.set_updated_at();
    """
    )

    op.execute(
        """
        CREATE TRIGGER trg_chunks_set_updated_at
            BEFORE UPDATE ON zero_admin.chunks
            FOR EACH ROW EXECUTE FUNCTION zero_admin.set_updated_at();
    """
    )

    op.execute(
        """
        CREATE TRIGGER trg_event_outbox_set_updated_at
            BEFORE UPDATE ON zero_admin.event_outbox
            FOR EACH ROW EXECUTE FUNCTION zero_admin.set_updated_at();
    """
    )


def downgrade() -> None:
    """Downgrade schema v1 inbox - remove all tables"""

    # Remove triggers first
    op.execute("DROP TRIGGER IF EXISTS trg_event_outbox_set_updated_at ON zero_admin.event_outbox;")
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_set_updated_at ON zero_admin.chunks;")
    op.execute("DROP TRIGGER IF EXISTS trg_parsed_items_set_updated_at ON zero_admin.parsed_items;")
    op.execute("DROP TRIGGER IF EXISTS trg_inbox_items_set_updated_at ON zero_admin.inbox_items;")

    # Remove indexes
    op.drop_index("ix_event_outbox_status", table_name="event_outbox", schema="zero_admin")
    op.drop_index("ix_event_outbox_created_at", table_name="event_outbox", schema="zero_admin")
    op.drop_index("ix_chunks_seq_no", table_name="chunks", schema="zero_admin")
    op.drop_index("ix_chunks_parsed_item_id", table_name="chunks", schema="zero_admin")
    op.drop_index("ix_parsed_items_inbox_item_id", table_name="parsed_items", schema="zero_admin")
    op.drop_index("ix_parsed_items_created_at", table_name="parsed_items", schema="zero_admin")
    op.drop_index("ix_inbox_items_status", table_name="inbox_items", schema="zero_admin")
    op.drop_index("ix_inbox_items_created_at", table_name="inbox_items", schema="zero_admin")

    # Drop tables (order matters due to foreign keys)
    op.drop_table("dead_letters", schema="zero_admin")
    op.drop_table("processed_events", schema="zero_admin")
    op.drop_table("event_outbox", schema="zero_admin")
    op.drop_table("chunks", schema="zero_admin")
    op.drop_table("parsed_items", schema="zero_admin")
    op.drop_table("inbox_items", schema="zero_admin")
