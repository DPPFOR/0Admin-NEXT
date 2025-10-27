from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.mcp.server.adapters.archive.unpack import ArchiveUnpackAdapter


def _schema(path: str):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_archive_unpack_positive():
    schema = _schema("backend/mcp/contracts/archive.unpack/1.0.0/output.json")
    out = ArchiveUnpackAdapter.plan(path="artifacts/inbox/samples/archive/sample.zip", dry_run=True)
    Draft202012Validator(schema).validate(out)


def test_archive_unpack_negative():
    with pytest.raises(ValueError):
        ArchiveUnpackAdapter.plan(path="/tmp/sample.zip", dry_run=True)
