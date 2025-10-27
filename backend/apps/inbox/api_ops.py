import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    insert,
    select,
)

from backend.core.config import settings
from backend.core.observability.logging import hash_actor_token, logger
from backend.core.observability.metrics import (
    get_metrics,
    increment_ops_replay_attempts,
    increment_ops_replay_committed,
    record_ops_duration,
)
from backend.core.tenant.validator import loader

router = APIRouter(prefix="/api/v1/ops")


def _error(status_code: int, code: str, detail: str):
    raise HTTPException(status_code=status_code, detail={"error": code, "detail": detail})


def _auth_admin(authorization: str | None) -> tuple[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        _error(
            status.HTTP_401_UNAUTHORIZED, "unauthorized", "Missing or invalid Authorization header"
        )
    token = (
        authorization.split(" ", 1)[1].strip() if " " in authorization else authorization.strip()
    )
    allowed = [t.strip() for t in settings.ADMIN_TOKENS.split(",") if t.strip()]
    if not allowed or token not in allowed:
        _error(status.HTTP_403_FORBIDDEN, "forbidden", "Admin token required")
    return token, hash_actor_token(token)


def _tables(metadata: MetaData) -> tuple[Table, Table, Table]:
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
    processed_events = Table(
        "processed_events",
        metadata,
        Column("tenant_id", String, primary_key=True),
        Column("event_type", String, primary_key=True),
        Column("idempotency_key", String(128), primary_key=True),
        Column("created_at", DateTime(timezone=True)),
        extend_existing=True,
    )
    return event_outbox, dead_letters, processed_events


@router.get("/outbox", response_model=dict[str, Any])
def get_outbox_status(
    authorization: str | None = Header(None, alias="Authorization"),
    tenant_header: str | None = Header(None, alias="X-Tenant"),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()
    token, token_hash = _auth_admin(authorization)
    tenant_id = tenant_header or "*"
    trace_id = trace_header or str(uuid.uuid4())
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    event_outbox, _, _ = _tables(metadata)
    with engine.begin() as conn:
        if tenant_id and tenant_id != "*":
            rows = conn.execute(
                select(event_outbox.c.status, func.count().label("cnt"))
                .where(event_outbox.c.tenant_id == tenant_id)
                .group_by(event_outbox.c.status)
            ).fetchall()
        else:
            rows = conn.execute(
                select(event_outbox.c.status, func.count().label("cnt")).group_by(
                    event_outbox.c.status
                )
            ).fetchall()
    result = {r.status or "null": int(r.cnt) for r in rows}
    record_ops_duration((time.time() - start) * 1000.0)
    logger.info(
        "ops_outbox_status",
        extra={
            "actor_role": "admin",
            "actor_token_hash": token_hash,
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "duration_ms": (time.time() - start) * 1000.0,
        },
    )
    return {"outbox": result}


@router.get("/dlq", response_model=dict[str, Any])
def list_dlq(
    authorization: str | None = Header(None, alias="Authorization"),
    tenant_header: str | None = Header(None, alias="X-Tenant"),
    limit: int = 50,
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()
    token, token_hash = _auth_admin(authorization)
    trace_id = trace_header or str(uuid.uuid4())
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    _, dead_letters, _ = _tables(metadata)
    where = []
    if tenant_header:
        where.append(dead_letters.c.tenant_id == tenant_header)
    with engine.begin() as conn:
        rows = conn.execute(
            select(
                dead_letters.c.id,
                dead_letters.c.tenant_id,
                dead_letters.c.event_type,
                dead_letters.c.reason,
                dead_letters.c.created_at,
            )
            .where(*where)
            .order_by(dead_letters.c.created_at.desc())
            .limit(limit)
        ).fetchall()
    items = [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "event_type": r.event_type,
            "reason": r.reason,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]
    record_ops_duration((time.time() - start) * 1000.0)
    logger.info(
        "ops_dlq_list",
        extra={
            "actor_role": "admin",
            "actor_token_hash": token_hash,
            "tenant_id": tenant_header or "*",
            "trace_id": trace_id,
            "duration_ms": (time.time() - start) * 1000.0,
            "result_count": len(items),
        },
    )
    return {"items": items}


class ReplayRequest(BaseModel):
    ids: list[str] | None = None
    dry_run: bool | None = True
    limit: int | None = 50


@router.post("/dlq/replay", response_model=dict[str, Any])
def replay_dlq(
    body: ReplayRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    tenant_header: str | None = Header(None, alias="X-Tenant"),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()
    token, token_hash = _auth_admin(authorization)
    trace_id = trace_header or str(uuid.uuid4())
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    event_outbox, dead_letters, _ = _tables(metadata)

    where = []
    if tenant_header:
        where.append(dead_letters.c.tenant_id == tenant_header)
    if body.ids:
        where.append(dead_letters.c.id.in_(body.ids))
    limit = body.limit or 50
    with engine.begin() as conn:
        rows = conn.execute(
            select(
                dead_letters.c.id,
                dead_letters.c.tenant_id,
                dead_letters.c.event_type,
                dead_letters.c.payload_json,
            )
            .where(*where)
            .order_by(dead_letters.c.created_at)
            .limit(limit)
        ).fetchall()

    increment_ops_replay_attempts(len(rows))
    if body.dry_run:
        record_ops_duration((time.time() - start) * 1000.0)
        logger.info(
            "ops_dlq_replay",
            extra={
                "actor_role": "admin",
                "actor_token_hash": token_hash,
                "tenant_id": tenant_header or "*",
                "trace_id": trace_id,
                "selected": len(rows),
                "committed": 0,
                "dry_run": True,
                "duration_ms": (time.time() - start) * 1000.0,
            },
        )
        return {"selected": len(rows), "committed": 0}

    committed = 0
    with engine.begin() as conn:
        for r in rows:
            try:
                conn.execute(
                    insert(event_outbox).values(
                        id=str(uuid.uuid4()),
                        tenant_id=r.tenant_id,
                        event_type=r.event_type,
                        schema_version="1.0",
                        idempotency_key=None,
                        trace_id=str(uuid.uuid4()),
                        payload_json=r.payload_json,
                        status="pending",
                        created_at=func.now(),
                    )
                )
                conn.execute(delete(dead_letters).where(dead_letters.c.id == r.id))
                committed += 1
            except Exception:
                continue

    increment_ops_replay_committed(committed)
    record_ops_duration((time.time() - start) * 1000.0)
    logger.info(
        "ops_dlq_replay",
        extra={
            "actor_role": "admin",
            "actor_token_hash": token_hash,
            "tenant_id": tenant_header or "*",
            "trace_id": trace_id,
            "selected": len(rows),
            "committed": committed,
            "duration_ms": (time.time() - start) * 1000.0,
        },
    )
    return {"selected": len(rows), "committed": committed}


@router.get("/metrics", response_model=dict[str, Any])
def get_metrics_admin(
    authorization: str | None = Header(None, alias="Authorization"),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    token, token_hash = _auth_admin(authorization)
    trace_id = trace_header or str(uuid.uuid4())
    logger.info(
        "ops_metrics",
        extra={"actor_role": "admin", "actor_token_hash": token_hash, "trace_id": trace_id},
    )
    return get_metrics()


@router.get("/tenants", response_model=dict[str, Any])
def list_tenants(
    authorization: str | None = Header(None, alias="Authorization"),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    token, token_hash = _auth_admin(authorization)
    trace_id = trace_header or str(uuid.uuid4())
    source, version, count, allow = loader.info()
    logger.info(
        "ops_tenants",
        extra={
            "actor_role": "admin",
            "actor_token_hash": token_hash,
            "trace_id": trace_id,
            "count": count,
            "source": source,
            "version": version,
        },
    )
    return {"source": source, "version": version, "count": count, "tenants": sorted(list(allow))}
