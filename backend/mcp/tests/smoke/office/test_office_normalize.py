from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.mcp.server.adapters.office.word_normalize import WordNormalizeAdapter
from backend.mcp.server.adapters.office.powerpoint_normalize import PowerPointNormalizeAdapter
from backend.mcp.server.adapters.office.excel_normalize import ExcelNormalizeAdapter


def _schema(path: str):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_word_normalize():
    schema = _schema("backend/mcp/contracts/office.word.normalize/1.0.0/output.json")
    out = WordNormalizeAdapter.plan(path="artifacts/inbox/samples/office/sample.docx", dry_run=True)
    Draft202012Validator(schema).validate(out)


def test_powerpoint_normalize():
    schema = _schema("backend/mcp/contracts/office.powerpoint.normalize/1.0.0/output.json")
    out = PowerPointNormalizeAdapter.plan(path="artifacts/inbox/samples/office/sample.pptx", dry_run=True)
    Draft202012Validator(schema).validate(out)


def test_excel_normalize():
    schema = _schema("backend/mcp/contracts/office.excel.normalize/1.0.0/output.json")
    out = ExcelNormalizeAdapter.plan(path="artifacts/inbox/samples/excel/sample.xlsx", dry_run=True)
    Draft202012Validator(schema).validate(out)


@pytest.mark.parametrize("bad", ["../x", "/x"]) 
def test_office_negative(bad):
    with pytest.raises(ValueError):
        WordNormalizeAdapter.plan(path=bad, dry_run=True)
