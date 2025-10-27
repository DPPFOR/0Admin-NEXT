"""Create outbox schema and events table

Revision ID: 20250214_outbox_events
Revises: 20251020_read_model_views
Create Date: 2025-02-14 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250214_outbox_events"
down_revision: str | None = "20251020_read_model_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS outbox")

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "next_attempt_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        schema="outbox",
    )

    op.create_index(
        "ix_outbox_events_status_next_attempt_at",
        "events",
        ["status", "next_attempt_at"],
        schema="outbox",
    )
    op.create_index(
        "ix_outbox_events_topic_status",
        "events",
        ["topic", "status"],
        schema="outbox",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_topic_status",
        table_name="events",
        schema="outbox",
    )
    op.drop_index(
        "ix_outbox_events_status_next_attempt_at",
        table_name="events",
        schema="outbox",
    )
    op.drop_table("events", schema="outbox")
    op.execute("DROP SCHEMA IF EXISTS outbox CASCADE")
