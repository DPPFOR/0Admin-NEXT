from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass
class ParsedItemDTO:
    tenant_id: str
    content_hash: str
    doc_type: str
    payload: dict[str, Any]
    amount: Decimal | None = None
    invoice_no: str | None = None
    due_date: date | None = None
    quality_flags: list[str] = field(default_factory=list)
    doctype: str = "unknown"
    quality_status: str = "needs_review"
    confidence: Decimal = Decimal("0")
    rules: list[dict[str, str]] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Decimal | None = None


@dataclass
class ParsedItemChunkDTO:
    parsed_item_id: str  # may be temp/placeholder before insert
    seq: int
    kind: str
    payload: dict[str, Any]


@dataclass
class ProcessResult:
    parsed_item_id: str
    action: str
    chunk_count: int
