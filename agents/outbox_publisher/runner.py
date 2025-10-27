from __future__ import annotations

import signal
import threading
import time
import time as _time
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from agents.outbox_publisher.policy import next_attempt_time
from agents.outbox_publisher.transports import StdoutTransport, WebhookTransport
from backend.core.config import settings
from backend.core.observability.logging import logger
from backend.core.observability.metrics import (
    increment_publisher_attempts,
    increment_publisher_failures,
    increment_publisher_sent,
    increment_tenant_unknown_dropped,
    record_publish_duration,
    record_publisher_lag,
)
from backend.core.tenant.validator import validate_tenant


def tables(metadata: MetaData) -> tuple[Table, Table]:
    event_outbox = Table(
        "event_outbox",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String),
        Column("event_type", String),
        Column("schema_version", String(16)),
        Column("idempotency_key", String(128)),
        Column("trace_id", String(64)),
        Column("payload_json", Text),
        Column("status", String),
        Column("attempt_count", Integer),
        Column("next_attempt_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True)),
        extend_existing=True,
    )
    dead_letters = Table(
        "dead_letters",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String),
        Column("event_type", String),
        Column("reason", String),
        Column("payload_json", Text),
        Column("created_at", DateTime(timezone=True)),
        extend_existing=True,
    )
    return event_outbox, dead_letters


def get_transport():
    if settings.PUBLISH_TRANSPORT == "webhook":
        return WebhookTransport()
    return StdoutTransport()


def run_once(engine: Engine | None = None, batch_size: int | None = None) -> int:
    """Publish up to batch_size pending outbox events.

    Returns number of events processed (sent, failed, or retried)."""
    engine = engine or create_engine(settings.database_url, future=True)
    metadata = MetaData()
    event_outbox, dead_letters = tables(metadata)
    limit = batch_size or settings.PUBLISH_BATCH_SIZE
    now = datetime.now(UTC)

    transport = get_transport()

    with engine.begin() as conn:
        rows = conn.execute(
            select(
                event_outbox.c.id,
                event_outbox.c.tenant_id,
                event_outbox.c.event_type,
                event_outbox.c.schema_version,
                event_outbox.c.idempotency_key,
                event_outbox.c.trace_id,
                event_outbox.c.payload_json,
                event_outbox.c.attempt_count,
                event_outbox.c.created_at,
            )
            .where((event_outbox.c.status == "pending") | (event_outbox.c.status.is_(None)))
            .where(
                (event_outbox.c.next_attempt_at.is_(None)) | (event_outbox.c.next_attempt_at <= now)
            )
            .order_by(event_outbox.c.created_at)
            .limit(limit)
        ).fetchall()

    processed = 0
    for row in rows:
        t0 = time.time()
        lag_ms = 0.0
        try:
            with engine.begin() as conn:
                # Lease
                upd = conn.execute(
                    update(event_outbox)
                    .where(event_outbox.c.id == row.id)
                    .where((event_outbox.c.status == "pending") | (event_outbox.c.status.is_(None)))
                    .values(status="processing")
                )
                if upd.rowcount == 0:
                    continue

                lag_ms = (now - (row.created_at or now)).total_seconds() * 1000.0
                try:
                    if row.created_at:
                        record_publisher_lag(lag_ms)
                except Exception:
                    pass

            # Publish
            increment_publisher_attempts()
            # Tenant policy check prior to publish
            v = validate_tenant(row.tenant_id)
            if not v.ok:
                with engine.begin() as conn:
                    conn.execute(
                        insert(dead_letters).values(
                            id=str(uuid4()),
                            tenant_id=row.tenant_id or "unknown",
                            event_type=row.event_type,
                            reason="tenant_unknown",
                            payload_json=row.payload_json or "{}",
                            created_at=now,
                        )
                    )
                    conn.execute(
                        update(event_outbox)
                        .where(event_outbox.c.id == row.id)
                        .values(status="failed")
                    )
                try:
                    increment_tenant_unknown_dropped()
                except Exception:
                    pass
                processed += 1
                continue
            res = transport.publish(
                row.tenant_id, row.event_type, row.payload_json or "{}", row.trace_id
            )
            ok = bool(res.ok)
            with engine.begin() as conn:
                if ok:
                    conn.execute(
                        update(event_outbox)
                        .where(event_outbox.c.id == row.id)
                        .values(status="sent")
                    )
                    increment_publisher_sent()
                    logger.info(
                        "published",
                        extra={
                            "tenant_id": row.tenant_id,
                            "event_type": row.event_type,
                            "attempt": (row.attempt_count or 0) + 1,
                            "transport": transport.name,
                            "status": "sent",
                            "duration_ms": (time.time() - t0) * 1000.0,
                        },
                    )
                else:
                    # Handle failure
                    attempts = (row.attempt_count or 0) + 1
                    if res.error == "unsupported_scheme":
                        # Non-retriable policy violation: fail immediately
                        conn.execute(
                            insert(dead_letters).values(
                                id=str(uuid4()),
                                tenant_id=row.tenant_id,
                                event_type=row.event_type,
                                reason=res.error,
                                payload_json=row.payload_json or "{}",
                                created_at=now,
                            )
                        )
                        conn.execute(
                            update(event_outbox)
                            .where(event_outbox.c.id == row.id)
                            .values(status="failed")
                        )
                        increment_publisher_failures()
                    else:
                        if attempts >= settings.PUBLISH_RETRY_MAX:
                            conn.execute(
                                insert(dead_letters).values(
                                    id=str(uuid4()),
                                    tenant_id=row.tenant_id,
                                    event_type=row.event_type,
                                    reason=res.error or "publish_failed",
                                    payload_json=row.payload_json or "{}",
                                    created_at=now,
                                )
                            )
                            conn.execute(
                                update(event_outbox)
                                .where(event_outbox.c.id == row.id)
                                .values(status="failed")
                            )
                            increment_publisher_failures()
                        else:
                            na = next_attempt_time(now, attempts)
                            conn.execute(
                                update(event_outbox)
                                .where(event_outbox.c.id == row.id)
                                .values(
                                    status="pending", attempt_count=attempts, next_attempt_at=na
                                )
                            )
                    logger.info(
                        "publish_failed" if not ok else "published",
                        extra={
                            "tenant_id": row.tenant_id,
                            "event_type": row.event_type,
                            "attempt": (row.attempt_count or 0) + 1,
                            "transport": transport.name,
                            "status": "sent" if ok else "failed",
                            "duration_ms": (time.time() - t0) * 1000.0,
                        },
                    )
            processed += 1
        except Exception:
            processed += 1
        finally:
            try:
                record_publish_duration((time.time() - t0) * 1000.0)
            except Exception:
                pass

    return processed


_stop_event = threading.Event()


def _setup_signals() -> None:
    def _handler(signum, frame):  # noqa: ARG001
        _stop_event.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def run_forever(service_mode: bool = True) -> int:
    """Run publisher loop with poll interval and signal handling.

    - service_mode=True: continuous loop; sleep when idle.
    - service_mode=False (timer mode): exit 0 on idle batch (no work), else keep looping until idle.
    Returns recommended exit code: 0 on normal stop/idle, 1 on fatal config error.
    """
    _setup_signals()

    # Fatal config validation
    if settings.PUBLISH_TRANSPORT == "webhook" and not settings.WEBHOOK_URL:
        logger.error(
            "publisher_config_error", extra={"reason": "WEBHOOK_URL missing for webhook transport"}
        )
        return 1

    poll_ms = max(0, int(getattr(settings, "PUBLISH_POLL_INTERVAL_MS", 1000)))
    exit_code = 0
    while not _stop_event.is_set():
        try:
            processed = run_once(batch_size=settings.PUBLISH_BATCH_SIZE)
        except Exception as e:
            logger.error("publisher_run_error", extra={"error": str(e)})
            processed = 0
        if processed == 0:
            if not service_mode:
                break
            if poll_ms > 0:
                _time.sleep(poll_ms / 1000.0)
        else:
            # immediate next iteration to drain backlog
            continue

    return exit_code
