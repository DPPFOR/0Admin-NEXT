from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from backend.core.config import settings
from backend.core.outbox import publisher
from tools.flows.outbox_consume_one import consume_one

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("OUTBOX_DB_URL") or os.getenv("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not RUN_DB_TESTS or not DB_URL,
    reason="Set RUN_DB_TESTS=1 and DATABASE_URL/OUTBOX_DB_URL for outbox DB tests.",
)


def _ensure_outbox_ready(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS outbox"))
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "ops/alembic")
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    command.upgrade(cfg, "head")


def _clear_outbox(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM outbox.events"))


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    engine = sa.create_engine(DB_URL, future=True)
    try:
        _ensure_outbox_ready(engine)
        settings.database_url = DB_URL
        publisher._get_engine.cache_clear()
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _cleanup_outbox(engine: Engine) -> Iterator[None]:
    _clear_outbox(engine)
    yield
    _clear_outbox(engine)


def _fetch_event(engine: Engine, event_id: str) -> dict:
    metadata = sa.MetaData()
    events = publisher.get_outbox_events_table(metadata)
    with engine.begin() as conn:
        row = conn.execute(
            sa.select(
                events.c.id,
                events.c.topic,
                events.c.status,
                events.c.attempt_count,
                events.c.next_attempt_at,
                events.c.created_at,
                events.c.payload,
            ).where(events.c.id == event_id)
        ).mappings().first()
        if not row:
            raise AssertionError(f"Event {event_id} not found")
        return dict(row)


def test_enqueue_event_persists_row(engine: Engine) -> None:
    event_id = str(publisher.enqueue_event("InboxItemAnalysisReady", {"sample": "payload"}))
    row = _fetch_event(engine, event_id)
    assert row["topic"] == "InboxItemAnalysisReady"
    assert row["status"] == "pending"
    assert row["attempt_count"] == 0
    assert isinstance(row["created_at"], datetime)
    assert row["created_at"].tzinfo is not None
    assert row["next_attempt_at"] <= datetime.now(timezone.utc)


def test_consumer_processes_once(engine: Engine) -> None:
    event_id = str(publisher.enqueue_event("InboxItemAnalysisReady", {"sample": "payload"}))
    processed = consume_one(engine)
    assert processed is True

    row = _fetch_event(engine, event_id)
    assert row["status"] == "processed"
    assert row["attempt_count"] == 0

    # Idempotent: second run should not reprocess the same event
    processed_again = consume_one(engine)
    assert processed_again is False

    row_after = _fetch_event(engine, event_id)
    assert row_after["status"] == "processed"
    assert row_after["attempt_count"] == 0
