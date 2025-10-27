from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.mcp.server.adapters.data_quality.tables_validate import (
    DataQualityTablesValidateAdapter,
)


def _schema(path: str):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_dq_tables_positive():
    schema = _schema("backend/mcp/contracts/data_quality.tables.validate/1.0.0/output.json")
    out = DataQualityTablesValidateAdapter.plan(
        paths=["artifacts/inbox/samples/excel/sample.xlsx"], dry_run=True
    )
    Draft202012Validator(schema).validate(out)


def test_dq_tables_negative():
    with pytest.raises(ValueError):
        DataQualityTablesValidateAdapter.plan(paths=["../escape.csv"], dry_run=True)
