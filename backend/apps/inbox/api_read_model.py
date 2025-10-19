from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from backend.apps.inbox.read_model.query import (
    ReadModelError,
    fetch_invoices_latest,
    fetch_items_needing_review,
    fetch_tenant_summary,
)


logger = logging.getLogger("inbox.read_model.api")

router = APIRouter(prefix="/inbox/read", tags=["inbox-read"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def require_tenant(tenant: UUID = Query(..., alias="tenant")) -> str:
    return str(tenant)


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


def _log(event: str, *, tenant_id: str, count: int, trace_id: Optional[str]) -> None:
    logger.info(
        event,
        extra={
            "tenant_id": tenant_id,
            "count": count,
            "trace_id": trace_id or "",
        },
    )


@router.get("/invoices")
def list_invoices(
    response: Response,
    tenant_id: str = Depends(require_tenant),
    limit: int = Query(DEFAULT_LIMIT, ge=0, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
) -> List[Dict[str, Any]]:
    try:
        items = fetch_invoices_latest(tenant_id, limit=limit, offset=offset)
    except (ReadModelError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    serialized = _serialize(items)
    response.headers["X-Total-Count"] = str(len(serialized))
    _log("read_model_invoices", tenant_id=tenant_id, count=len(serialized), trace_id=trace_id)
    return serialized


@router.get("/review")
def list_items_needing_review(
    response: Response,
    tenant_id: str = Depends(require_tenant),
    limit: int = Query(DEFAULT_LIMIT, ge=0, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
) -> List[Dict[str, Any]]:
    try:
        items = fetch_items_needing_review(tenant_id, limit=limit, offset=offset)
    except (ReadModelError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    serialized = _serialize(items)
    response.headers["X-Total-Count"] = str(len(serialized))
    _log("read_model_review", tenant_id=tenant_id, count=len(serialized), trace_id=trace_id)
    return serialized


@router.get("/summary")
def get_summary(
    tenant_id: str = Depends(require_tenant),
    trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
) -> Dict[str, Any]:
    try:
        summary = fetch_tenant_summary(tenant_id)
    except ReadModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if summary is None:
        raise HTTPException(status_code=404, detail="summary_not_found")

    serialized = _serialize(summary)
    _log("read_model_summary", tenant_id=tenant_id, count=1, trace_id=trace_id)
    return serialized
