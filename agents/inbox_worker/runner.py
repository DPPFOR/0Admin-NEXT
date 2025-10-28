import json
import signal
import threading
import time
import time as _time
from datetime import UTC, datetime, timedelta
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
from sqlalchemy.exc import IntegrityError

from agents.inbox_worker.pipeline import maybe_chunk, parse_content, route_mime_to_doc_type
from backend.core.config import settings
from backend.core.observability.logging import logger
from backend.core.observability.metrics import (
    add_chunk_bytes,
    increment_parse_failures,
    increment_parsed_total,
    increment_tenant_unknown_dropped,
    record_parse_duration,
)
from backend.core.tenant.validator import validate_tenant


def tables(metadata):
    event_outbox = Table(
        "event_outbox",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("event_type", String, nullable=False),
        Column("schema_version", String(16), nullable=False),
        Column("idempotency_key", String(128)),
        Column("trace_id", String(64)),
        Column("payload_json", Text, nullable=False),
        Column("status", String, default="pending"),
        Column("attempt_count", Integer, default=0),
        Column("next_attempt_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True)),
        extend_existing=True,
    )

    processed_events = Table(
        "processed_events",
        metadata,
        Column("tenant_id", String, primary_key=True),
        Column("event_type", String, primary_key=True),
        Column("idempotency_key", String(128), primary_key=True),
        Column("created_at", DateTime(timezone=True), default=datetime.now(UTC)),
        extend_existing=True,
    )

    inbox_items = Table(
        "inbox_items",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("status", String, nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("uri", Text, nullable=False),
        Column("source", String(64)),
        Column("filename", Text),
        Column("mime", String(128)),
        Column("updated_at", DateTime(timezone=True)),
        extend_existing=True,
    )

    parsed_items = Table(
        "parsed_items",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("inbox_item_id", String, nullable=False),
        Column("payload_json", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), default=datetime.now(UTC)),
        extend_existing=True,
    )

    chunks = Table(
        "chunks",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("parsed_item_id", String, nullable=False),
        Column("inbox_item_id", String, nullable=False),
        Column("seq_no", Integer, nullable=False),
        Column("text", Text, nullable=False),
        Column("token_count", Integer, nullable=True),
        Column("created_at", DateTime(timezone=True), default=datetime.now(UTC)),
        extend_existing=True,
    )

    dead_letters = Table(
        "dead_letters",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("event_type", String, nullable=False),
        Column("reason", String, nullable=False),
        Column("payload_json", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), default=datetime.now(UTC)),
        extend_existing=True,
    )

    return event_outbox, processed_events, inbox_items, parsed_items, chunks, dead_letters


def _read_file_from_uri(uri: str) -> bytes:
    if not uri.startswith("file://"):
        raise OSError("Unsupported storage URI for worker")
    path = uri[len("file://") :]
    with open(path, "rb") as f:
        return f.read()


def _backoff_seconds(attempt: int) -> int:
    steps = [int(x.strip()) for x in settings.PARSER_BACKOFF_STEPS.split(",") if x.strip()]
    idx = min(attempt - 1, len(steps) - 1)
    return steps[idx] if steps else 30


def run_once(engine: Engine | None = None, batch_size: int | None = None) -> int:
    """Process up to batch_size pending InboxItemValidated events.

    Returns number of processed events (success or dedup/skip)."""
    engine = engine or create_engine(settings.database_url, future=True)
    metadata = MetaData()
    event_outbox, processed_events, inbox_items, parsed_items, chunks, dead_letters = tables(
        metadata
    )

    limit = batch_size or settings.WORKER_BATCH_SIZE
    now = datetime.now(UTC)

    processed = 0
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
            )
            .where(event_outbox.c.event_type == "InboxItemValidated")
            .where((event_outbox.c.status == "pending") | (event_outbox.c.status.is_(None)))
            .where(
                (event_outbox.c.next_attempt_at.is_(None)) | (event_outbox.c.next_attempt_at <= now)
            )
            .order_by(event_outbox.c.created_at)
            .limit(limit)
        ).fetchall()

    for row in rows:
        try:
            with engine.begin() as conn:
                # Lease: set status to processing
                upd = conn.execute(
                    update(event_outbox)
                    .where(event_outbox.c.id == row.id)
                    .where((event_outbox.c.status == "pending") | (event_outbox.c.status.is_(None)))
                    .values(status="processing")
                )
                if upd.rowcount == 0:
                    continue

                payload = json.loads(row.payload_json)
                tenant_id = row.tenant_id
                # Tenant policy check
                v = validate_tenant(tenant_id)
                if not v.ok:
                    # Unknown tenants are non-retriable: DLQ
                    conn.execute(
                        insert(dead_letters).values(
                            id=str(uuid4()),
                            tenant_id=tenant_id or "unknown",
                            event_type=row.event_type,
                            reason="tenant_unknown",
                            payload_json=row.payload_json,
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
                inbox_item_id = payload.get("inbox_item_id")
                mime = payload.get("mime")
                uri = payload.get("uri")
                idem_key = row.idempotency_key or payload.get("content_hash") or inbox_item_id

                # Idempotency: insert processed_events; skip if exists
                try:
                    conn.execute(
                        insert(processed_events).values(
                            tenant_id=tenant_id,
                            event_type=row.event_type,
                            idempotency_key=idem_key,
                            created_at=now,
                        )
                    )
                except IntegrityError:
                    # already processed; mark sent and continue
                    conn.execute(
                        update(event_outbox)
                        .where(event_outbox.c.id == row.id)
                        .values(status="sent")
                    )
                    processed += 1
                    continue

                # Read file
                data = _read_file_from_uri(uri)
                # MIME allowlist enforcement for parsing stage
                allow = [m.strip() for m in settings.MIME_ALLOWLIST.split(",")]
                if not mime or mime not in allow:
                    raise ValueError("unsupported_mime")

                t0 = time.time()
                try:
                    parsed = parse_content(mime, data)
                    parse_ms = (time.time() - t0) * 1000.0
                    try:
                        record_parse_duration(parse_ms)
                    except Exception:
                        pass
                    # Persist parsed_items
                    parsed_id = str(uuid4())
                    conn.execute(
                        insert(parsed_items).values(
                            id=parsed_id,
                            tenant_id=tenant_id,
                            inbox_item_id=inbox_item_id,
                            payload_json=json.dumps(parsed),
                            created_at=now,
                        )
                    )
                    # Optional chunking from parsed text if exists
                    text_for_chunks = None
                    # choose a best-effort text field
                    # For simplicity, serialize parsed and chunk its JSON if very large
                    serialized = json.dumps(parsed)
                    text_for_chunks = serialized
                    has_chunks, chunks_map = maybe_chunk(text_for_chunks)
                    if has_chunks:
                        seq = 1
                        for _k, txt in chunks_map.items():
                            conn.execute(
                                insert(chunks).values(
                                    id=str(uuid4()),
                                    tenant_id=tenant_id,
                                    parsed_item_id=parsed_id,
                                    inbox_item_id=inbox_item_id,
                                    seq_no=seq,
                                    text=txt,
                                    token_count=len(txt.split()),
                                    created_at=now,
                                )
                            )
                            seq += 1
                        try:
                            total_bytes = sum(len(v.encode("utf-8")) for v in chunks_map.values())
                            add_chunk_bytes(total_bytes)
                        except Exception:
                            pass

                    # Update inbox status
                    conn.execute(
                        update(inbox_items)
                        .where(inbox_items.c.id == inbox_item_id)
                        .values(status="parsed", updated_at=now)
                    )

                    # Emit Parsed event
                    parsed_payload = {
                        "inbox_item_id": inbox_item_id,
                        "parsed_item_id": parsed_id,
                        "doc_type": route_mime_to_doc_type(mime or ""),
                        "has_chunks": bool(has_chunks),
                        "summary_fields": {
                            k: v
                            for k, v in parsed.items()
                            if k in ("invoice_no", "amount", "due_date", "doc_type")
                        },
                    }
                    try:
                        conn.execute(
                            insert(event_outbox).values(
                                id=str(uuid4()),
                                tenant_id=tenant_id,
                                event_type="InboxItemParsed",
                                schema_version="1.0",
                                idempotency_key=idem_key,
                                trace_id=row.trace_id,
                                payload_json=json.dumps(parsed_payload),
                                status="pending",
                                created_at=now,
                            )
                        )
                    except IntegrityError:
                        # Idempotent guard hit; continue
                        pass

                    # Mark source event sent
                    conn.execute(
                        update(event_outbox)
                        .where(event_outbox.c.id == row.id)
                        .values(status="sent")
                    )
                    try:
                        increment_parsed_total()
                    except Exception:
                        pass
                    logger.info(
                        "parsed",
                        extra={
                            "trace_id": row.trace_id or "",
                            "tenant_id": tenant_id,
                            "inbox_item_id": inbox_item_id,
                            "doc_type": route_mime_to_doc_type(mime or ""),
                            "parse_ms": parse_ms,
                            "status": "parsed",
                        },
                    )
                    processed += 1
                except ValueError as ve:
                    # validation_error, unsupported_mime, parse_error map to non-retriable
                    reason = str(ve)
                    conn.execute(
                        update(inbox_items)
                        .where(inbox_items.c.id == inbox_item_id)
                        .values(status="error", updated_at=now)
                    )
                    fail_payload = {
                        "inbox_item_id": inbox_item_id,
                        "reason": reason.split(":")[0],
                        "error_class": "validation_error",
                        "retriable": False,
                    }
                    try:
                        conn.execute(
                            insert(event_outbox).values(
                                id=str(uuid4()),
                                tenant_id=tenant_id,
                                event_type="InboxItemParseFailed",
                                schema_version="1.0",
                                idempotency_key=idem_key,
                                trace_id=row.trace_id,
                                payload_json=json.dumps(fail_payload),
                                status="pending",
                                created_at=now,
                            )
                        )
                    except IntegrityError:
                        pass
                    conn.execute(
                        update(event_outbox)
                        .where(event_outbox.c.id == row.id)
                        .values(status="failed")
                    )
                    try:
                        increment_parse_failures()
                    except Exception:
                        pass
                    logger.info(
                        "parse_failed",
                        extra={
                            "trace_id": row.trace_id or "",
                            "tenant_id": tenant_id,
                            "inbox_item_id": inbox_item_id,
                            "doc_type": route_mime_to_doc_type(mime or ""),
                            "status": "error",
                            "reason": reason.split(":")[0],
                        },
                    )
                    processed += 1
                except Exception:
                    # retriable io_error
                    attempts = (row.attempt_count or 0) + 1
                    next_at = now + timedelta(seconds=_backoff_seconds(attempts))
                    conn.execute(
                        update(event_outbox)
                        .where(event_outbox.c.id == row.id)
                        .values(
                            status="pending",
                            attempt_count=attempts,
                            next_attempt_at=next_at,
                        )
                    )
                    if attempts >= settings.PARSER_RETRY_MAX:
                        # move to dead letters
                        conn.execute(
                            insert(dead_letters).values(
                                id=str(uuid4()),
                                tenant_id=tenant_id,
                                event_type=row.event_type,
                                reason="io_error",
                                payload_json=row.payload_json,
                                created_at=now,
                            )
                        )
                        conn.execute(
                            update(event_outbox)
                            .where(event_outbox.c.id == row.id)
                            .values(status="failed")
                        )
                    continue
        except Exception:
            # move on to next event
            continue

    return processed


_stop_event = threading.Event()


def _setup_signals() -> None:
    def _handler(signum, frame):  # noqa: ARG001
        _stop_event.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def run_forever(service_mode: bool = True) -> int:
    """Run inbox parsing loop with poll interval and signal handling.

    - service_mode=True: continuous loop; sleep when idle.
    - service_mode=False (timer mode): exit 0 on idle batch; otherwise continue until idle.
    Returns 0 on normal stop/idle, 1 on fatal config error.
    """
    _setup_signals()

    # Fatal config validation (basic)
    if not settings.database_url:
        logger.error("worker_config_error", extra={"reason": "DATABASE_URL missing"})
        return 1

    poll_ms = max(0, int(getattr(settings, "WORKER_POLL_INTERVAL_MS", 1000)))
    exit_code = 0
    while not _stop_event.is_set():
        try:
            processed = run_once(batch_size=settings.WORKER_BATCH_SIZE)
        except Exception as e:
            logger.error("worker_run_error", extra={"error": str(e)})
            processed = 0
        if processed == 0:
            if not service_mode:
                break
            if poll_ms > 0:
                _time.sleep(poll_ms / 1000.0)
        else:
            continue

    return exit_code
