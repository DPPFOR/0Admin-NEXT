from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional


_AMOUNT_RE = re.compile(r"^\d+(?:\.\d{1,2})?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_currency_amount(s: str) -> bool:
    return bool(_AMOUNT_RE.match(s))


def validate_iso_date(s: str) -> bool:
    return bool(_DATE_RE.match(s))


def validate_tables_shape(tables: Any) -> List[Dict[str, Any]]:
    if tables is None:
        return []
    if not isinstance(tables, list):
        raise ValueError("invalid tables: must be list")
    out: List[Dict[str, Any]] = []
    for t in tables:
        if not isinstance(t, dict):
            raise ValueError("invalid table: must be object")
        headers = t.get("headers", [])
        rows = t.get("rows", [])
        if not isinstance(headers, list) or not all(isinstance(h, str) for h in headers):
            raise ValueError("invalid table.headers")
        if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
            raise ValueError("invalid table.rows")
        # Soft limits
        if len(headers) > 200:
            pass
        if sum(len(r) for r in rows) > 10_000 * max(1, len(headers)):
            pass
        out.append({"headers": headers, "rows": rows})
    return out


def validate_artifact_minimum(flow: Dict[str, Any], tenant_id: str) -> None:
    if not isinstance(flow, dict):
        raise ValueError("invalid artifact: not an object")
    if flow.get("tenant_id") != tenant_id:
        raise ValueError("invalid artifact: tenant mismatch")
    fp = flow.get("fingerprints", {})
    if not isinstance(fp, dict) or not fp.get("content_hash"):
        raise ValueError("invalid artifact: missing fingerprints.content_hash")
    if "pipeline" not in flow or not isinstance(flow.get("pipeline"), list):
        raise ValueError("invalid artifact: missing pipeline")
    if "extracted" not in flow or not isinstance(flow.get("extracted"), dict):
        raise ValueError("invalid artifact: missing extracted")


def parse_amount(value: Optional[str]) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not validate_currency_amount(value):
        raise ValueError("invalid amount format")
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - Decimal gives precise context
        raise ValueError("invalid amount format") from exc


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not validate_iso_date(value):
        raise ValueError("invalid due_date format")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("invalid due_date format") from exc
