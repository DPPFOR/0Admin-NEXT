from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .dto import InvoiceRowDTO, NeedsReviewRowDTO, PaymentRowDTO, TenantSummaryDTO

VALID_STATUSES = {"accepted", "needs_review", "rejected"}


class ReadModelError(RuntimeError):
    """Raised when the read-model cannot be accessed."""


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ReadModelError("DATABASE_URL environment variable is required for read-model queries")
    return url


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return create_engine(_database_url(), future=True)


def _validate_pagination(limit: int, offset: int) -> None:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if offset < 0:
        raise ValueError("offset must be non-negative")


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_float(value) -> float:
    if isinstance(value, float):
        return value
    if value is None:
        return 0.0
    return float(value)


def _validate_filters(min_conf: float | None) -> float | None:
    if min_conf is None:
        return None
    if isinstance(min_conf, (int, float)):
        value = float(min_conf)
    else:
        value = float(str(min_conf))
    if value < 0 or value > 100:
        raise ValueError("min_conf must be between 0 and 100")
    return value


def _filter_clause(
    base_conditions: list[str],
    *,
    min_conf: float | None = None,
    status: str | None = None,
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    if min_conf is not None:
        params["min_conf"] = _validate_filters(min_conf)
        base_conditions.append("confidence >= :min_conf")
    if status:
        normalized = str(status)
        if normalized not in VALID_STATUSES:
            raise ValueError("status must be one of accepted, needs_review, rejected")
        params["status"] = str(status)
        base_conditions.append("quality_status = :status")
    where = " AND ".join(base_conditions)
    return where, params


def fetch_invoices_latest(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    *,
    min_conf: float | None = None,
    status: str | None = None,
) -> list[InvoiceRowDTO]:
    _validate_pagination(limit, offset)
    conditions = ["tenant_id = :tenant_id"]
    where, dynamic_params = _filter_clause(conditions, min_conf=min_conf, status=status)
    stmt = text(
        f"""
        SELECT id,
               tenant_id,
               content_hash,
               amount,
               invoice_no,
               due_date,
               quality_status,
               confidence,
               flags,
               mvr_preview,
               mvr_score,
               created_at
        FROM inbox_parsed.v_invoices_latest
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    with _engine().connect() as conn:
        rows = conn.execute(
            stmt,
            {
                "tenant_id": tenant_id,
                "limit": limit,
                "offset": offset,
                **dynamic_params,
            },
        ).mappings()
        return [
            InvoiceRowDTO(
                id=UUID(str(row["id"])),
                tenant_id=UUID(str(row["tenant_id"])),
                content_hash=str(row["content_hash"]),
                amount=_to_decimal(row["amount"]),
                invoice_no=row["invoice_no"],
                due_date=row["due_date"],
                quality_status=str(row["quality_status"]),
                confidence=_to_float(row["confidence"]),
                created_at=row["created_at"],
                flags=row["flags"] or {},
                mvr_preview=bool(row["mvr_preview"]),
                mvr_score=_to_decimal(row["mvr_score"]),
            )
            for row in rows
        ]


def fetch_payments_latest(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    *,
    min_conf: float | None = None,
    status: str | None = None,
) -> list[PaymentRowDTO]:
    _validate_pagination(limit, offset)
    conditions = ["tenant_id = :tenant_id"]
    where, dynamic_params = _filter_clause(conditions, min_conf=min_conf, status=status)
    stmt = text(
        f"""
        SELECT id,
               tenant_id,
               content_hash,
               amount,
               currency,
               counterparty,
               payment_date,
               quality_status,
               confidence,
               flags,
               mvr_preview,
               mvr_score,
               created_at
        FROM inbox_parsed.v_payments_latest
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    with _engine().connect() as conn:
        rows = conn.execute(
            stmt,
            {
                "tenant_id": tenant_id,
                "limit": limit,
                "offset": offset,
                **dynamic_params,
            },
        ).mappings()
        return [
            PaymentRowDTO(
                id=UUID(str(row["id"])),
                tenant_id=UUID(str(row["tenant_id"])),
                content_hash=str(row["content_hash"]),
                amount=_to_decimal(row["amount"]),
                currency=row["currency"],
                counterparty=row["counterparty"],
                payment_date=row["payment_date"],
                quality_status=str(row["quality_status"]),
                confidence=_to_float(row["confidence"]),
                created_at=row["created_at"],
                flags=row["flags"] or {},
                mvr_preview=bool(row["mvr_preview"]),
                mvr_score=_to_decimal(row["mvr_score"]),
            )
            for row in rows
        ]


def fetch_items_needing_review(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    *,
    min_conf: float | None = None,
    status: str | None = None,
) -> list[NeedsReviewRowDTO]:
    _validate_pagination(limit, offset)
    conditions = ["tenant_id = :tenant_id"]
    where, dynamic_params = _filter_clause(conditions, min_conf=min_conf, status=status)
    stmt = text(
        f"""
        SELECT id,
               tenant_id,
               doctype,
               quality_status,
               confidence,
               created_at,
               content_hash,
               flags,
               mvr_preview,
               mvr_score
        FROM inbox_parsed.v_items_needing_review
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    with _engine().connect() as conn:
        rows = conn.execute(
            stmt,
            {
                "tenant_id": tenant_id,
                "limit": limit,
                "offset": offset,
                **dynamic_params,
            },
        ).mappings()
        return [
            NeedsReviewRowDTO(
                id=UUID(str(row["id"])),
                tenant_id=UUID(str(row["tenant_id"])),
                doc_type=str(row["doctype"]),
                quality_status=str(row["quality_status"]),
                confidence=_to_float(row["confidence"]),
                created_at=row["created_at"],
                content_hash=str(row["content_hash"]),
                flags=row["flags"] or {},
                mvr_preview=bool(row["mvr_preview"]),
                mvr_score=_to_decimal(row["mvr_score"]),
            )
            for row in rows
        ]


def fetch_tenant_summary(tenant_id: str) -> TenantSummaryDTO | None:
    stmt = text(
        """
        SELECT tenant_id,
               total_items,
               invoices,
               payments,
               others,
               NULL as cnt_needing_review,
               NULL as cnt_mvr_preview,
               avg_confidence,
               NULL as avg_mvr_score
        FROM inbox_parsed.v_inbox_by_tenant
        WHERE tenant_id = :tenant_id
        """
    )
    with _engine().connect() as conn:
        row = conn.execute(stmt, {"tenant_id": tenant_id}).mappings().first()
        if not row:
            return None
        avg_conf = row["avg_confidence"]
        return TenantSummaryDTO(
            tenant_id=UUID(str(row["tenant_id"])),
            cnt_items=int(row["total_items"] or 0),
            cnt_invoices=int(row["invoices"] or 0),
            cnt_payments=int(row["payments"] or 0),
            cnt_other=int(row["others"] or 0),
            cnt_needing_review=int(row["cnt_needing_review"] or 0),
            cnt_mvr_preview=int(row["cnt_mvr_preview"] or 0),
            avg_confidence=float(avg_conf) if avg_conf is not None else None,
            avg_mvr_score=float(row["avg_mvr_score"]) if row["avg_mvr_score"] is not None else None,
        )


def query_payments(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    *,
    min_conf: float | None = None,
    status: str | None = None,
) -> list[PaymentRowDTO]:
    return fetch_payments_latest(
        tenant_id,
        limit=limit,
        offset=offset,
        min_conf=min_conf,
        status=status,
    )


def query_review(
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    *,
    min_conf: float | None = None,
    status: str | None = None,
) -> list[NeedsReviewRowDTO]:
    return fetch_items_needing_review(
        tenant_id,
        limit=limit,
        offset=offset,
        min_conf=min_conf,
        status=status,
    )
