"""Consume a single pending outbox event and dispatch it to a topic handler."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.core.config import settings
from backend.core.observability.logging import get_logger, init_logging
from backend.core.outbox.publisher import get_outbox_events_table


BACKOFF_SECONDS = 60

init_logging()
logger = get_logger("tools.flows.outbox_consume_one")


def _get_engine() -> Engine:
    return sa.create_engine(settings.database_url, future=True)


def _handle_inbox_item_analysis_ready(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a JSON object")
    # Ensure payload is JSON-compatible
    json.dumps(dict(payload))


HANDLERS: dict[str, Callable[[Mapping[str, Any]], None]] = {
    "InboxItemAnalysisReady": _handle_inbox_item_analysis_ready,
}


def consume_one(engine: Engine | None = None) -> bool:
    """Consume a single pending outbox event if available."""
    engine = engine or _get_engine()
    metadata = sa.MetaData()
    events = get_outbox_events_table(metadata)
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        stmt = (
            sa.select(
                events.c.id,
                events.c.topic,
                events.c.payload,
                events.c.attempt_count,
                events.c.created_at,
            )
            .where(events.c.status == "pending")
            .where(events.c.next_attempt_at <= now)
            .order_by(events.c.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = conn.execute(stmt).mappings().first()
        if not row:
            logger.info("outbox_consume_idle", extra={"status": "idle"})
            return False

        conn.execute(
            sa.update(events)
            .where(events.c.id == row["id"])
            .values(status="processing")
        )

    event_id = str(row["id"])
    topic = row["topic"]
    payload = row["payload"]
    attempt_count = int(row["attempt_count"] or 0)

    handler = HANDLERS.get(topic)
    if handler is None:
        logger.warning("outbox_handler_missing", extra={"event_id": event_id, "topic": topic})
        _schedule_retry(engine, events, event_id, attempt_count)
        return False

    try:
        handler(payload)
    except Exception as exc:
        logger.warning(
            "outbox_handler_error",
            extra={"event_id": event_id, "topic": topic, "error_type": exc.__class__.__name__},
        )
        _schedule_retry(engine, events, event_id, attempt_count)
        return False

    with engine.begin() as conn:
        conn.execute(
            sa.update(events)
            .where(events.c.id == event_id)
            .values(status="processed", next_attempt_at=datetime.now(timezone.utc))
        )
    logger.info("outbox_event_processed", extra={"event_id": event_id, "topic": topic})
    return True


def _schedule_retry(engine: Engine, events: sa.Table, event_id: str, attempt_count: int) -> None:
    now = datetime.now(timezone.utc)
    delay_seconds = BACKOFF_SECONDS * max(1, attempt_count + 1)
    next_attempt = now + timedelta(seconds=delay_seconds)
    with engine.begin() as conn:
        conn.execute(
            sa.update(events)
            .where(events.c.id == event_id)
            .values(
                status="pending",
                attempt_count=attempt_count + 1,
                next_attempt_at=next_attempt,
            )
        )
    logger.info(
        "outbox_event_rescheduled",
        extra={"event_id": event_id, "delay_s": delay_seconds},
    )


def main() -> int:
    processed = consume_one()
    return 0 if processed or processed is False else 1


if __name__ == "__main__":
    sys.exit(main())
