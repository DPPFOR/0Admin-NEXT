import io
import json
import os
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

try:
    from backend.app import create_app
    from backend.core.config import settings
    from backend.core.observability.metrics import get_metrics
except ModuleNotFoundError as exc:
    pytest.skip(f"backend package not importable: {exc}", allow_module_level=True)

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = getattr(settings, "database_url", None)

if not RUN_DB_TESTS or not DB_URL:
    pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL", allow_module_level=True)

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = ARTIFACTS_DIR / "u3-p1b-smoke.json"


def _db_engine():
    url = os.environ.get("DATABASE_URL", settings.database_url)
    return create_engine(url, future=True)


def _db_count(sql: str, params: dict) -> int:
    eng = _db_engine()
    with eng.begin() as conn:
        return conn.execute(text(sql), params).scalar() or 0


def _table_exists(name: str) -> bool:
    eng = _db_engine()
    with eng.begin() as conn:
        res = conn.execute(text(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_name = :name
            )
        """
        ), {"name": name}).scalar()
    return bool(res)


def _make_pdf(size_mb: int = 2) -> bytes:
    head = b"%PDF-1.4\n"
    body = b"\0" * (size_mb * 1024 * 1024 - len(head))
    return head + body


def _make_exe(size_kb: int = 10) -> bytes:
    return os.urandom(size_kb * 1024)


def _assert_alembic_head(report: dict) -> None:
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", settings.database_url))
    script = ScriptDirectory.from_config(cfg)
    heads = set(script.get_heads())

    engine = _db_engine()
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()

    ok = current in heads
    report_step = {"name": "precheck_alembic_head", "current": current, "heads": list(heads), "status": "passed" if ok else "failed"}
    report.setdefault("prechecks", []).append(report_step)
    if not ok:
        REPORT_PATH.write_text(json.dumps(report, indent=2))
        pytest.fail(f"Alembic not at head: current={current}, heads={','.join(heads)}")


def test_u3_p1b_smoke(monkeypatch, caplog):
    # Preflight: DB connectivity and required tables
    try:
        eng = _db_engine()
        with eng.begin() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.fail(f"DATABASE_URL not usable: {e}")

    assert _table_exists("inbox_items"), "inbox_items table missing"
    assert _table_exists("event_outbox"), "event_outbox table missing"

    # Ensure storage backend is file and path is writable
    monkeypatch.setenv("STORAGE_BACKEND", "file")
    storage_base = os.environ.get("STORAGE_BASE_URI", settings.STORAGE_BASE_URI)
    base_path = storage_base.replace("file://", "")
    Path(base_path).mkdir(parents=True, exist_ok=True)

    report = {"tests": []}

    # Alembic must be at head
    _assert_alembic_head(report)

    # Token and tenant
    token = os.environ.get("SMOKE_TOKEN", "smoke-token")
    monkeypatch.setenv("AUTH_SERVICE_TOKENS", token)
    tenant_id = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))

    app = create_app()
    client = TestClient(app)

    # T-1: Happy Path
    pdf_bytes = _make_pdf(2)
    caplog.set_level("INFO")
    resp = client.post(
        "/api/v1/inbox/items/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant": tenant_id,
        },
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"source": "upload"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "validated"
    assert body["tenant_id"] == tenant_id
    assert body["mime"] == "application/pdf"
    assert body["duplicate"] is False

    inbox_id = body["id"]
    content_hash = body["content_hash"]

    c_inbox = _db_count(
        "SELECT COUNT(*) FROM inbox_items WHERE tenant_id=:t AND content_hash=:h",
        {"t": tenant_id, "h": content_hash},
    )
    assert c_inbox == 1
    c_outbox = _db_count(
        "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemValidated' AND payload_json::json->>'inbox_item_id'=:i",
        {"t": tenant_id, "i": inbox_id},
    )
    assert c_outbox == 1
    report["tests"].append({"name": "T-1 Happy", "status": "passed"})

    # T-2: Duplicate
    resp2 = client.post(
        "/api/v1/inbox/items/upload",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"source": "upload"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["duplicate"] is True
    report["tests"].append({"name": "T-2 Duplicate", "status": "passed"})

    # T-3: Unsupported MIME (.exe)
    exe_bytes = _make_exe(10)
    r3 = client.post(
        "/api/v1/inbox/items/upload",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        files={"file": ("bad.exe", io.BytesIO(exe_bytes), "application/octet-stream")},
    )
    assert r3.status_code == 400
    assert r3.json()["detail"]["error"] == "unsupported_mime"
    report["tests"].append({"name": "T-3 MIME", "status": "passed"})

    # T-4: Size limit (MAX_UPLOAD_MB=1)
    old_limit = settings.MAX_UPLOAD_MB
    try:
        settings.MAX_UPLOAD_MB = 1
        r4 = client.post(
            "/api/v1/inbox/items/upload",
            headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
            files={"file": ("big.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert r4.status_code == 400
        assert r4.json()["detail"]["error"] == "size_limit"
    finally:
        settings.MAX_UPLOAD_MB = old_limit
    report["tests"].append({"name": "T-4 Size", "status": "passed"})

    # Metrics presence
    metrics = get_metrics()
    assert "inbox_items_total" in metrics

    # Health endpoints
    health = client.get("/healthz")
    ready = client.get("/readyz")
    assert health.status_code == 200
    assert ready.status_code == 200

    # Cleanup report
    REPORT_PATH.write_text(json.dumps(report, indent=2))
