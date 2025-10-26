from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.mcp.server.adapters.pdf.text_extract import PdfTextExtractAdapter
from backend.mcp.server.adapters.pdf.ocr_extract import PdfOCRExtractAdapter
from backend.mcp.server.adapters.pdf.tables_extract import PdfTablesExtractAdapter


def _schema(path: str):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_pdf_text_extract():
    schema = _schema("backend/mcp/contracts/pdf.text_extract/1.0.0/output.json")
    out = PdfTextExtractAdapter.plan(path="artifacts/inbox/samples/pdf/sample.pdf", dry_run=True)
    Draft202012Validator(schema).validate(out)


def test_pdf_ocr_extract():
    schema = _schema("backend/mcp/contracts/pdf.ocr_extract/1.0.0/output.json")
    out = PdfOCRExtractAdapter.plan(path="artifacts/inbox/samples/pdf/sample.pdf", dry_run=True)
    Draft202012Validator(schema).validate(out)


def test_pdf_tables_extract():
    schema = _schema("backend/mcp/contracts/pdf.tables_extract/1.0.0/output.json")
    out = PdfTablesExtractAdapter.plan(path="artifacts/inbox/samples/pdf/sample.pdf", dry_run=True)
    Draft202012Validator(schema).validate(out)


@pytest.mark.parametrize("bad", ["../pdf", "/pdf"]) 
def test_pdf_negative(bad):
    with pytest.raises(ValueError):
        PdfTextExtractAdapter.plan(path=bad, dry_run=True)
