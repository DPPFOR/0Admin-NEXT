from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.mcp.server.adapters.security.pii_redact import SecurityPIIRedactAdapter


def _schema(path: str):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_pii_redact_positive():
    schema = _schema("backend/mcp/contracts/security.pii.redact/1.0.0/output.json")
    out = SecurityPIIRedactAdapter.plan(
        paths=["artifacts/inbox/samples/office/sample.docx"], dry_run=True
    )
    Draft202012Validator(schema).validate(out)


def test_pii_redact_negative():
    with pytest.raises(ValueError):
        SecurityPIIRedactAdapter.plan(paths=["/root/secret.txt"], dry_run=True)
