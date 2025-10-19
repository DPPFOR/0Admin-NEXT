from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ValidationError(Exception):
    pass


def _is_hex64(s: str) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)


DOC_TYPES = {"invoice", "payment", "unknown"}


@dataclass
class ExtractedTable:
    name: str
    columns: List[str]


@dataclass
class InboxLocalFlowResultDTO:
    tenant_id: str
    content_hash: str
    doc_type: str
    extracted_tables: List[ExtractedTable] = field(default_factory=list)
    amount: Optional[str] = None
    invoice_no: Optional[str] = None
    due_date: Optional[str] = None
    quality_flags: List[str] = field(default_factory=list)
    pii_summary: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id:
            raise ValidationError("tenant_id required")
        if not _is_hex64(self.content_hash):
            raise ValidationError("content_hash must be 64 hex chars")
        if self.doc_type not in DOC_TYPES:
            raise ValidationError("doc_type invalid")
        if self.due_date is not None and not isinstance(self.due_date, str):
            raise ValidationError("due_date must be YYYY-MM-DD string when provided")
        for t in self.extracted_tables:
            if not isinstance(t.name, str) or not isinstance(t.columns, list):
                raise ValidationError("invalid ExtractedTable")

