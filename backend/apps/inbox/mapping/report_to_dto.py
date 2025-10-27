from __future__ import annotations

import importlib.util as _iu
import os as _os
import sys as _sys
from typing import Any

try:
    from .dto import ExtractedTable, InboxLocalFlowResultDTO  # type: ignore
except Exception:  # allow direct loading without package context
    _spec = _iu.spec_from_file_location("dto", _os.path.join(_os.path.dirname(__file__), "dto.py"))
    _dto_mod = _iu.module_from_spec(_spec)
    assert _spec and _spec.loader
    _sys.modules[_spec.name] = _dto_mod
    _spec.loader.exec_module(_dto_mod)  # type: ignore[union-attr]
    ExtractedTable = _dto_mod.ExtractedTable
    InboxLocalFlowResultDTO = _dto_mod.InboxLocalFlowResultDTO


def report_to_dto(flow_report: dict[str, Any]) -> InboxLocalFlowResultDTO:
    tenant_id = flow_report.get("tenant_id", "")
    content_hash = flow_report.get("fingerprints", {}).get("content_hash", "")
    # naive doc type classification based on pipeline presence
    pipeline: list[str] = flow_report.get("pipeline", [])
    if any(s.startswith("pdf.") for s in pipeline) or any(
        s.startswith("office.") for s in pipeline
    ):
        doc_type = "unknown"
    else:
        doc_type = "unknown"

    # extracted tables if present
    tables = []
    for t in flow_report.get("extracted", {}).get("tables", []):
        name = t.get("name", "table") if isinstance(t, dict) else "table"
        cols = t.get("columns", []) if isinstance(t, dict) else []
        tables.append(ExtractedTable(name=name, columns=[str(c) for c in cols]))

    quality_flags = []
    quality = flow_report.get("quality", {})
    if not quality.get("valid", True):
        quality_flags.append("invalid")

    pii_summary = {"planned_steps": len(flow_report.get("pii", {}).get("steps", []))}

    dto = InboxLocalFlowResultDTO(
        tenant_id=tenant_id,
        content_hash=content_hash,
        doc_type=doc_type,
        extracted_tables=tables,
        amount=None,
        invoice_no=None,
        due_date=None,
        quality_flags=quality_flags,
        pii_summary=pii_summary,
    )
    dto.validate()
    return dto
