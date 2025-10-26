from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from datetime import date, timedelta
import importlib.util as _iu


def _load_mapper():
    spec = _iu.spec_from_file_location("mapper", "backend/apps/inbox/importer/mapper.py")
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


mapper = _load_mapper()


def _base_flow() -> dict:
    today = date.today()
    return {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "fingerprints": {"content_hash": "hash-good"},
        "pipeline": ["pdf.text_extract", "pdf.tables_extract"],
        "mime": "application/pdf",
        "doc_type": "unknown",
        "amount": "199.90",
        "invoice_no": "INV-12345",
        "due_date": today.isoformat(),
        "quality": {"valid": True, "issues": []},
        "flags": {
            "enable_ocr": False,
            "enable_browser": False,
            "enable_table_boost": False,
            "mvr_preview": False,
        },
        "extracted": {
            "tables": [
                {
                    "headers": ["item", "amount"],
                    "rows": [["service", "199.90"]],
                }
            ]
        },
        "pii": {"steps": []},
    }


def test_mapper_good_invoice_sets_quality():
    data = _base_flow()
    item, chunks = mapper.artifact_to_dtos(data)
    assert item.doctype == "invoice"
    assert item.quality_status == "accepted"
    assert item.confidence == Decimal("100.00")
    assert item.flags.get("enable_ocr") is False
    assert item.mvr_preview is False
    assert item.mvr_score is None
    assert item.rules == []
    assert item.amount == Decimal("199.90")
    assert item.invoice_no == "INV-12345"
    assert item.due_date is not None
    assert len(chunks) == 1


def test_mapper_bad_invoice_collects_rules():
    data = deepcopy(_base_flow())
    data["fingerprints"]["content_hash"] = "hash-bad"
    data["amount"] = ""
    data["due_date"] = (date.today() - timedelta(days=400)).isoformat()
    data["invoice_no"] = "!!"
    data["quality"] = {"valid": False, "issues": ["ocr_warning"]}
    data["flags"] = {"ocr_warning": True}
    data["extracted"]["tables"] = []

    item, chunks = mapper.artifact_to_dtos(data)
    assert item.doctype == "unknown"
    assert item.quality_status == "rejected"
    assert item.confidence == Decimal("0.00")
    assert len(item.rules) >= 3
    codes = {rule["code"] for rule in item.rules}
    assert "invoice.amount.missing" in codes
    assert "invoice.number.invalid" in codes
    assert "invoice.table.missing" in codes
    assert item.quality_flags and "ocr_warning" in item.quality_flags
    assert chunks == []


def test_mapper_without_enforcement_keeps_unknown_doctype():
    data = _base_flow()
    item, _ = mapper.artifact_to_dtos(data, enforce_invoice=False)
    assert item.doctype == "other"
    assert item.quality_status == "needs_review"
    assert item.confidence == Decimal("50.00")
    assert item.flags.get("enable_table_boost") is False
