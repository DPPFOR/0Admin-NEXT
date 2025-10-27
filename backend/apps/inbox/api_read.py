import base64
import hmac
import json
import time
import uuid
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, create_engine, select

from backend.core.config import settings
from backend.core.observability.logging import logger, set_tenant_id
from backend.core.observability.metrics import (
    increment_inbox_read,
    increment_parsed_read,
    record_read_duration,
)
from backend.core.tenant.context import require_tenant

router = APIRouter(prefix="/api/v1")


def _error(status_code: int, code: str, detail: str):
    raise HTTPException(status_code=status_code, detail={"error": code, "detail": detail})


def _hmac_sign(data: dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":")).encode()
    sig = hmac.new(settings.CURSOR_HMAC_KEY.encode(), payload, sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + sig).decode()


def _hmac_verify(cursor: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        payload, sig = raw.rsplit(b".", 1)
        expected = hmac.new(settings.CURSOR_HMAC_KEY.encode(), payload, sha256).digest()
        if not hmac.compare_digest(sig, expected):
            _error(status.HTTP_400_BAD_REQUEST, "invalid_cursor", "Cursor signature invalid")
        data = json.loads(payload.decode())
        return data
    except Exception:
        _error(status.HTTP_400_BAD_REQUEST, "invalid_cursor", "Cursor malformed")


def _tables(metadata: MetaData) -> tuple[Table, Table]:
    inbox_items = Table(
        "inbox_items",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String),
        Column("status", String),
        Column("content_hash", String(64)),
        Column("mime", String(128)),
        Column("source", String(64)),
        Column("created_at", DateTime(timezone=True)),
        extend_existing=True,
    )
    parsed_items = Table(
        "parsed_items",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String),
        Column("inbox_item_id", String),
        Column("payload_json", Text),
        Column("created_at", DateTime(timezone=True)),
        extend_existing=True,
    )
    return inbox_items, parsed_items


class InboxItemOut(BaseModel):
    id: str
    status: str
    tenant_id: str
    content_hash: str
    mime: str | None = None
    source: str | None = None
    created_at: str | None = None


class ParsedItemOut(BaseModel):
    id: str
    tenant_id: str
    inbox_item_id: str
    created_at: str | None = None
    doc_type: str | None = None
    invoice_no: str | None = None
    amount: str | None = None
    due_date: str | None = None


def _auth_tenant(tenant_header: str | None) -> str:
    if not tenant_header:
        _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "Missing X-Tenant header")
    try:
        tid = str(uuid.UUID(tenant_header))
        set_tenant_id(tid)
        return tid
    except Exception:
        _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "Invalid X-Tenant header")


@router.get("/inbox/items", response_model=dict[str, Any])
def list_inbox_items(
    tenant_id: str = Depends(require_tenant),
    limit: int = Query(50, ge=1, le=1000),
    cursor: str | None = Query(None),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()
    # tenant_id validated by dependency
    limit = min(limit, settings.READ_MAX_LIMIT)
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    inbox_items, _ = _tables(metadata)

    where = [inbox_items.c.tenant_id == tenant_id]
    if cursor:
        c = _hmac_verify(cursor)
        where.append((inbox_items.c.created_at, inbox_items.c.id) < (c["created_at"], c["id"]))

    with engine.begin() as conn:
        rows = conn.execute(
            select(
                inbox_items.c.id,
                inbox_items.c.status,
                inbox_items.c.tenant_id,
                inbox_items.c.content_hash,
                inbox_items.c.mime,
                inbox_items.c.source,
                inbox_items.c.created_at,
            )
            .where(*where)
            .order_by(inbox_items.c.created_at.desc(), inbox_items.c.id.desc())
            .limit(limit)
        ).fetchall()

    items = [
        InboxItemOut(
            id=r.id,
            status=r.status,
            tenant_id=r.tenant_id,
            content_hash=r.content_hash,
            mime=r.mime,
            source=r.source,
            created_at=str(r.created_at) if r.created_at else None,
        ).model_dump()
        for r in rows
    ]
    next_cursor = None
    if rows:
        last = rows[-1]
        next_cursor = _hmac_sign({"created_at": str(last.created_at), "id": last.id})

    increment_inbox_read()
    record_read_duration((time.time() - start) * 1000.0)
    trace_id = trace_header or str(uuid.uuid4())
    logger.info(
        "read_inbox_items",
        extra={
            "tenant_id": tenant_id,
            "actor_role": "user",
            "trace_id": trace_id,
            "endpoint": "/inbox/items",
            "result_count": len(items),
            "duration_ms": (time.time() - start) * 1000.0,
        },
    )
    return {"items": items, "next": next_cursor}


@router.get("/inbox/items/{item_id}", response_model=InboxItemOut)
def get_inbox_item(
    item_id: str,
    tenant_id: str = Depends(require_tenant),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()
    # validated
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    inbox_items, _ = _tables(metadata)
    with engine.begin() as conn:
        r = conn.execute(
            select(
                inbox_items.c.id,
                inbox_items.c.status,
                inbox_items.c.tenant_id,
                inbox_items.c.content_hash,
                inbox_items.c.mime,
                inbox_items.c.source,
                inbox_items.c.created_at,
            )
            .where(inbox_items.c.id == item_id)
            .where(inbox_items.c.tenant_id == tenant_id)
        ).fetchone()
    if not r:
        _error(status.HTTP_404_NOT_FOUND, "not_found", "Item not found")
    increment_inbox_read()
    record_read_duration((time.time() - start) * 1000.0)
    trace_id = trace_header or str(uuid.uuid4())
    return InboxItemOut(
        id=r.id,
        status=r.status,
        tenant_id=r.tenant_id,
        content_hash=r.content_hash,
        mime=r.mime,
        source=r.source,
        created_at=str(r.created_at) if r.created_at else None,
    )


@router.get("/parsed/items", response_model=dict[str, Any])
def list_parsed_items(
    tenant_id: str = Depends(require_tenant),
    limit: int = Query(50, ge=1, le=1000),
    cursor: str | None = Query(None),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()
    # validated
    limit = min(limit, settings.READ_MAX_LIMIT)
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    _, parsed_items = _tables(metadata)

    where = [parsed_items.c.tenant_id == tenant_id]
    if cursor:
        c = _hmac_verify(cursor)
        where.append((parsed_items.c.created_at, parsed_items.c.id) < (c["created_at"], c["id"]))

    with engine.begin() as conn:
        rows = conn.execute(
            select(
                parsed_items.c.id,
                parsed_items.c.tenant_id,
                parsed_items.c.inbox_item_id,
                parsed_items.c.payload_json,
                parsed_items.c.created_at,
            )
            .where(*where)
            .order_by(parsed_items.c.created_at.desc(), parsed_items.c.id.desc())
            .limit(limit)
        ).fetchall()

    items: list[dict[str, Any]] = []
    for r in rows:
        payload = {}
        try:
            pj = json.loads(r.payload_json or "{}")
            payload = {k: pj.get(k) for k in ("doc_type", "invoice_no", "amount", "due_date")}
        except Exception:
            payload = {}
        out = ParsedItemOut(
            id=r.id,
            tenant_id=r.tenant_id,
            inbox_item_id=r.inbox_item_id,
            created_at=str(r.created_at) if r.created_at else None,
            **payload,
        ).model_dump()
        items.append(out)

    next_cursor = None
    if rows:
        last = rows[-1]
        next_cursor = _hmac_sign({"created_at": str(last.created_at), "id": last.id})

    increment_parsed_read()
    record_read_duration((time.time() - start) * 1000.0)
    trace_id = trace_header or str(uuid.uuid4())
    logger.info(
        "read_parsed_items",
        extra={
            "tenant_id": tenant_id,
            "actor_role": "user",
            "trace_id": trace_id,
            "endpoint": "/parsed/items",
            "result_count": len(items),
            "duration_ms": (time.time() - start) * 1000.0,
        },
    )
    return {"items": items, "next": next_cursor}


@router.get("/parsed/items/{parsed_id}", response_model=ParsedItemOut)
def get_parsed_item(
    parsed_id: str,
    tenant_id: str = Depends(require_tenant),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()
    # validated
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    _, parsed_items = _tables(metadata)
    with engine.begin() as conn:
        r = conn.execute(
            select(
                parsed_items.c.id,
                parsed_items.c.tenant_id,
                parsed_items.c.inbox_item_id,
                parsed_items.c.payload_json,
                parsed_items.c.created_at,
            )
            .where(parsed_items.c.id == parsed_id)
            .where(parsed_items.c.tenant_id == tenant_id)
        ).fetchone()
    if not r:
        _error(status.HTTP_404_NOT_FOUND, "not_found", "Parsed item not found")
    pj = {}
    try:
        pj = json.loads(r.payload_json or "{}")
    except Exception:
        pj = {}
    increment_parsed_read()
    record_read_duration((time.time() - start) * 1000.0)
    trace_id = trace_header or str(uuid.uuid4())
    return ParsedItemOut(
        id=r.id,
        tenant_id=r.tenant_id,
        inbox_item_id=r.inbox_item_id,
        created_at=str(r.created_at) if r.created_at else None,
        doc_type=pj.get("doc_type"),
        invoice_no=pj.get("invoice_no"),
        amount=pj.get("amount"),
        due_date=pj.get("due_date"),
    )
