from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from typing import List, Optional
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .dto import InvoiceRowDTO, NeedsReviewRowDTO, TenantSummaryDTO


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


def _to_decimal(value) -> Optional[Decimal]:
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


def fetch_invoices_latest(tenant_id: str, limit: int = 50, offset: int = 0) -> List[InvoiceRowDTO]:
    _validate_pagination(limit, offset)
    stmt = text(
        """
        SELECT id,
               tenant_id,
               content_hash,
               amount,
               invoice_no,
               due_date,
               quality_status,
               confidence,
               created_at
        FROM inbox_parsed.v_invoices_latest
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    with _engine().connect() as conn:
        rows = conn.execute(
            stmt,
            {"tenant_id": tenant_id, "limit": limit, "offset": offset},
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
            )
            for row in rows
        ]


def fetch_items_needing_review(tenant_id: str, limit: int = 50, offset: int = 0) -> List[NeedsReviewRowDTO]:
    _validate_pagination(limit, offset)
    stmt = text(
        """
        SELECT id,
               tenant_id,
               doc_type,
               quality_status,
               confidence,
               created_at,
               content_hash
        FROM inbox_parsed.v_items_needing_review
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    with _engine().connect() as conn:
        rows = conn.execute(
            stmt,
            {"tenant_id": tenant_id, "limit": limit, "offset": offset},
        ).mappings()
        return [
            NeedsReviewRowDTO(
                id=UUID(str(row["id"])),
                tenant_id=UUID(str(row["tenant_id"])),
                doc_type=str(row["doc_type"]),
                quality_status=str(row["quality_status"]),
                confidence=_to_float(row["confidence"]),
                created_at=row["created_at"],
                content_hash=str(row["content_hash"]),
            )
            for row in rows
        ]


def fetch_tenant_summary(tenant_id: str) -> Optional[TenantSummaryDTO]:
    stmt = text(
        """
        SELECT tenant_id,
               cnt_items,
               cnt_invoices,
               cnt_needing_review,
               avg_confidence
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
            cnt_items=int(row["cnt_items"]),
            cnt_invoices=int(row["cnt_invoices"]),
            cnt_needing_review=int(row["cnt_needing_review"]),
            avg_confidence=float(avg_conf) if avg_conf is not None else None,
        )
