from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.mcp.server.adapters.email.gmail_fetch import GmailFetchAdapter
from backend.mcp.server.adapters.email.outlook_fetch import OutlookFetchAdapter


def _schema(path: str):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_gmail_fetch_positive():
    schema = _schema("backend/mcp/contracts/email.gmail.fetch/1.0.0/output.json")
    out = GmailFetchAdapter.plan(path="artifacts/inbox/samples/email/sample.eml", dry_run=True)
    Draft202012Validator(schema).validate(out)


def test_outlook_fetch_positive():
    schema = _schema("backend/mcp/contracts/email.outlook.fetch/1.0.0/output.json")
    out = OutlookFetchAdapter.plan(path="artifacts/inbox/samples/email/sample.msg", dry_run=True)
    Draft202012Validator(schema).validate(out)


@pytest.mark.parametrize("bad", ["../bad.msg", "/abs/path.msg"])
def test_email_fetch_negative(bad):
    with pytest.raises(ValueError):
        GmailFetchAdapter.plan(path=bad, dry_run=True)
