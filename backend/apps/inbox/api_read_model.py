from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

# from backend.core.tenant.context import require_tenant
from backend.apps.inbox.read_model.query import (
    ReadModelError,
    fetch_invoices_latest,
    fetch_items_needing_review,
    fetch_payments_latest,
    fetch_tenant_summary,
)

logger = logging.getLogger("inbox.read_model.api")

router = APIRouter(prefix="/inbox/read", tags=["inbox-read"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def require_tenant(
    tenant: str = Header(..., alias="X-Tenant-ID", convert_underscores=False)
) -> str:
    """Extract and validate tenant ID from X-Tenant-ID header."""
    try:
        return str(UUID(str(tenant)))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="invalid_tenant") from exc


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj):
        return {key: _serialize(value) for key, value in asdict(obj).items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return _serialize_value(obj)


def _log(event: str, *, tenant_id: str, count: int, trace_id: str | None) -> None:
    logger.info(
        event,
        extra={
            "tenant_id": tenant_id,
            "count": count,
            "trace_id": trace_id or "",
        },
    )


def _build_list_payload(
    response: Response,
    items: Any,
    *,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    serialized = _serialize(items)
    total = len(serialized)
    response.headers["X-Total-Count"] = str(total)
    return {
        "items": serialized,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/invoices")
def list_invoices(
    response: Response,
    tenant_id: str = Depends(require_tenant),
    limit: int = Query(DEFAULT_LIMIT, ge=0, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    min_conf: int | None = Query(None, ge=0, le=100),
    status: str | None = Query(None, regex="^(accepted|needs_review|rejected)$"),
    trace_id: str | None = Header(None, alias="X-Trace-ID"),
) -> dict[str, Any]:
    try:
        items = fetch_invoices_latest(
            tenant_id,
            limit=limit,
            offset=offset,
            min_conf=min_conf,
            status=status,
        )
    except (ReadModelError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = _build_list_payload(response, items, limit=limit, offset=offset)
    _log("read_model_invoices", tenant_id=tenant_id, count=payload["total"], trace_id=trace_id)
    return payload


@router.get("/payments")
def list_payments(
    response: Response,
    tenant_id: str = Depends(require_tenant),
    limit: int = Query(DEFAULT_LIMIT, ge=0, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    min_conf: int | None = Query(None, ge=0, le=100),
    status: str | None = Query(None, regex="^(accepted|needs_review|rejected)$"),
    trace_id: str | None = Header(None, alias="X-Trace-ID"),
) -> dict[str, Any]:
    try:
        items = fetch_payments_latest(
            tenant_id,
            limit=limit,
            offset=offset,
            min_conf=min_conf,
            status=status,
        )
    except (ReadModelError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = _build_list_payload(response, items, limit=limit, offset=offset)
    _log("read_model_payments", tenant_id=tenant_id, count=payload["total"], trace_id=trace_id)
    return payload


@router.get("/review")
def list_items_needing_review(
    response: Response,
    tenant_id: str = Depends(require_tenant),
    limit: int = Query(DEFAULT_LIMIT, ge=0, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    min_conf: int | None = Query(None, ge=0, le=100),
    status: str | None = Query(None, regex="^(accepted|needs_review|rejected)$"),
    trace_id: str | None = Header(None, alias="X-Trace-ID"),
) -> dict[str, Any]:
    try:
        items = fetch_items_needing_review(
            tenant_id,
            limit=limit,
            offset=offset,
            min_conf=min_conf,
            status=status,
        )
    except (ReadModelError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = _build_list_payload(response, items, limit=limit, offset=offset)
    _log("read_model_review", tenant_id=tenant_id, count=payload["total"], trace_id=trace_id)
    return payload


@router.get("/summary")
def get_summary(
    tenant_id: str = Depends(require_tenant),
    trace_id: str | None = Header(None, alias="X-Trace-ID"),
) -> dict[str, Any]:
    try:
        summary = fetch_tenant_summary(tenant_id)
    except ReadModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if summary is None:
        raise HTTPException(status_code=404, detail="summary_not_found")

    serialized = _serialize(summary)
    _log("read_model_summary", tenant_id=tenant_id, count=1, trace_id=trace_id)
    return serialized
