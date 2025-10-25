from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class ParsedItemDTO:
    tenant_id: str
    content_hash: str
    doc_type: str
    payload: Dict[str, Any]
    amount: Optional[Decimal] = None
    invoice_no: Optional[str] = None
    due_date: Optional[date] = None
    quality_flags: List[str] = field(default_factory=list)
    doctype: str = "unknown"
    quality_status: str = "needs_review"
    confidence: Decimal = Decimal("0")
    rules: List[Dict[str, str]] = field(default_factory=list)
    flags: Dict[str, Any] = field(default_factory=dict)
    mvr_preview: bool = False
    mvr_score: Optional[Decimal] = None


@dataclass
class ParsedItemChunkDTO:
    parsed_item_id: str  # may be temp/placeholder before insert
    seq: int
    kind: str
    payload: Dict[str, Any]


@dataclass
class ProcessResult:
    parsed_item_id: str
    action: str
    chunk_count: int
