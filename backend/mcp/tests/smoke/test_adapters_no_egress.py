from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from backend.mcp.server.adapters.etl_inbox_extract import ETLInboxExtractAdapter
from backend.mcp.server.adapters.inbox_read import DLQListAdapter, HealthCheckAdapter
from backend.mcp.server.adapters.ops_status import OutboxStatusAdapter
from backend.mcp.server.adapters.qa_smoke import QASmokeAdapter


def load_schema(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def block_egress(monkeypatch):
    # Block sockets
    import socket

    def _blocked(*args, **kwargs):  # pragma: no cover - just a guard
        raise RuntimeError("egress blocked")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    # Block subprocess and os.system
    import asyncio
    import os
    import subprocess

    for name in ("Popen", "call", "check_call", "check_output", "run"):
        monkeypatch.setattr(subprocess, name, _blocked)
    monkeypatch.setattr(os, "system", _blocked)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _blocked)

    # Block urllib/http client
    import http.client
    import ssl
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    monkeypatch.setattr(http.client, "HTTPConnection", _blocked)
    monkeypatch.setattr(http.client, "HTTPSConnection", _blocked)
    monkeypatch.setattr(ssl, "create_default_context", _blocked)


def test_health_check_output_validates_against_schema():
    schema = load_schema(Path("backend/mcp/contracts/ops.health_check/1.0.0/output.json"))
    out = HealthCheckAdapter.plan(version="1.0.0")
    Draft202012Validator(schema).validate(out)
    bad = dict(out)
    bad.pop("version")
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(bad)


def test_outbox_status_output_validates_against_schema():
    schema = load_schema(Path("backend/mcp/contracts/ops.outbox_status/1.0.0/output.json"))
    out = OutboxStatusAdapter.plan(tenant_id=None, window=None)
    Draft202012Validator(schema).validate(out)
    bad = {"counts": {"pending": 1, "processing": 0, "sent": 0}}  # missing failed
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(bad)


def test_dlq_list_output_validates_against_schema():
    schema = load_schema(Path("backend/mcp/contracts/ops.dlq_list/1.0.0/output.json"))
    out = DLQListAdapter.plan(tenant_id=None, limit=50, cursor=None)
    Draft202012Validator(schema).validate(out)
    bad = {"items": [], "next_cursor": "not_base64"}
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(bad)


def test_qa_smoke_output_validates_against_schema():
    schema = load_schema(Path("backend/mcp/contracts/qa.run_smoke/1.0.0/output.json"))
    out = QASmokeAdapter.plan(selection="read_ops", dry_run=True)
    Draft202012Validator(schema).validate(out)
    bad = {"summary": {"total": 1, "passed": 1, "failed": 0}}  # missing suites
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(bad)


def test_etl_inbox_extract_output_validates_against_schema():
    schema = load_schema(Path("backend/mcp/contracts/etl.inbox_extract/1.0.0/output.json"))
    out = ETLInboxExtractAdapter.plan(
        tenant_id="00000000-0000-4000-8000-000000000000",
        remote_url="https://example.com/x",
        dry_run=True,
    )
    Draft202012Validator(schema).validate(out)
    bad = {"plan": {"steps": [{}]}}  # step without name
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(bad)
