from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional, TypedDict, Literal


_AMOUNT_RE = re.compile(r"^\d+(?:\.\d{1,2})?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INVOICE_NO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_\/]{2,63}$")
_MAX_COLUMNS = 100
_MAX_ROWS = 5000
_REQUIRED_DUE_DATE_LOOKBACK_DAYS = 365


RuleLevel = Literal["error", "warning"]


class Rule(TypedDict):
    code: str
    level: RuleLevel
    message: str


RuleList = List[Rule]


def _rule(code: str, message: str, *, level: RuleLevel = "error") -> Rule:
    return {"code": code, "level": level, "message": message}


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


def validate_invoice_amount(value: Optional[Decimal]) -> RuleList:
    rules: RuleList = []
    if value is None:
        rules.append(_rule("invoice.amount.missing", "Invoice amount is required"))
        return rules

    if value <= Decimal("0"):
        rules.append(_rule("invoice.amount.invalid", "Invoice amount must be greater than zero"))
    return rules


def validate_invoice_due_date(value: Optional[date]) -> RuleList:
    rules: RuleList = []
    if value is None:
        rules.append(_rule("invoice.due_date.missing", "Invoice due date is required"))
        return rules

    min_allowed = date.today() - timedelta(days=_REQUIRED_DUE_DATE_LOOKBACK_DAYS)
    if value < min_allowed:
        rules.append(
            _rule(
                "invoice.due_date.implausible",
                "Invoice due date is too far in the past",
                level="warning",
            )
        )
    return rules


def validate_invoice_no(value: Optional[str]) -> RuleList:
    rules: RuleList = []
    if value in (None, ""):
        rules.append(_rule("invoice.number.missing", "Invoice number is required"))
        return rules

    if not isinstance(value, str):
        rules.append(_rule("invoice.number.type_error", "Invoice number must be a string"))
        return rules

    if not _INVOICE_NO_RE.match(value):
        rules.append(_rule("invoice.number.invalid", "Invoice number format is invalid"))
    return rules


def validate_table_shape(table: Dict[str, Any]) -> RuleList:
    if not isinstance(table, dict):
        raise ValueError("invalid table: must be object")

    headers = table.get("headers", [])
    rows = table.get("rows", [])
    if not isinstance(headers, list):
        raise ValueError("invalid table.headers")
    if not isinstance(rows, list):
        raise ValueError("invalid table.rows")

    rules: RuleList = []

    if len(headers) < 2:
        rules.append(_rule("invoice.table.columns_missing", "Invoice table must have at least two columns"))

    if any((not isinstance(h, str)) or (not h.strip()) for h in headers):
        rules.append(_rule("invoice.table.header_blank", "Invoice table headers must be non-empty strings"))

    if len(headers) > _MAX_COLUMNS:
        rules.append(
            _rule(
                "invoice.table.too_many_columns",
                f"Invoice table must have at most {_MAX_COLUMNS} columns",
                level="warning",
            )
        )

    if any(not isinstance(r, list) for r in rows):
        raise ValueError("invalid table.rows entries")

    row_count = len(rows)
    if row_count > _MAX_ROWS:
        rules.append(
            _rule(
                "invoice.table.too_many_rows",
                f"Invoice table must have at most {_MAX_ROWS} rows",
                level="warning",
            )
        )
    return rules


def compute_confidence(ctx: Mapping[str, Any]) -> int:
    score = 0
    if ctx.get("required_ok"):
        score += 40
    if ctx.get("table_ok"):
        score += 20
    if ctx.get("plausibility_ok"):
        score += 20
    if ctx.get("source_ok"):
        score += 20

    return max(0, min(100, int(score)))


def decide_quality_status(required_ok: bool, confidence: int) -> Literal["accepted", "needs_review", "rejected"]:
    if required_ok and confidence >= 70:
        return "accepted"
    if required_ok or confidence >= 50:
        return "needs_review"
    return "rejected"


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
