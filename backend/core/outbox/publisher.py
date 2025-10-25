"""Outbox publisher helper for enqueueing events."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Mapping
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine

from backend.core.config import settings
from backend.core.observability.logging import logger

_METADATA = MetaData()


def get_outbox_events_table(metadata: MetaData) -> Table:
    """Return the outbox.events table definition for the given metadata."""
    return sa.Table(
        "events",
        metadata,
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="outbox",
        extend_existing=True,
    )


_EVENTS = get_outbox_events_table(_METADATA)


@lru_cache(maxsize=1)
def _get_engine() -> Engine:
    """Create (and cache) the SQLAlchemy engine used for the outbox."""
    return sa.create_engine(settings.database_url, future=True)


def enqueue_event(topic: str, payload: Mapping[str, Any], *, delay_s: int = 0) -> UUID:
    """Persist an event into the outbox and return its UUID."""
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("topic must be a non-empty string")
    if delay_s < 0:
        raise ValueError("delay_s must be >= 0")

    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    payload_dict = dict(payload)

    try:
        json.dumps(payload_dict)
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be JSON serializable") from exc

    event_id = uuid4()
    now = datetime.now(timezone.utc)
    next_attempt = now + timedelta(seconds=delay_s)

    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.insert(_EVENTS).values(
                id=str(event_id),
                topic=topic,
                payload=payload_dict,
                status="pending",
                attempt_count=0,
                next_attempt_at=next_attempt,
                created_at=now,
            )
        )

    logger.info(
        "outbox_event_enqueued",
        extra={
            "event_id": str(event_id),
            "topic": topic,
            "delay_s": delay_s,
        },
    )
    return event_id


__all__ = ["enqueue_event", "get_outbox_events_table"]
