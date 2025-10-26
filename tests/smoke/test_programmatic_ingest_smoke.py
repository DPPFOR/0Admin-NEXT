import io
import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app import create_app
from backend.core.config import settings
from backend.apps.inbox import ingest as ingest_module
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext


ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = ARTIFACTS_DIR / "u3-p2-programmatic-smoke.json"


def _db_engine():
    url = os.environ.get("DATABASE_URL", settings.database_url)
    return create_engine(url, future=True)


def _db_count(sql: str, params: dict) -> int:
    eng = _db_engine()
    with eng.begin() as conn:
        return conn.execute(text(sql), params).scalar() or 0


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


def test_programmatic_ingest_smoke(monkeypatch, caplog):
    report = {"tests": []}

    # Preflight DB
    try:
        eng = _db_engine()
        with eng.begin() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.fail(f"DATABASE_URL not usable: {e}")

    _assert_alembic_head(report)

    # Configure token and storage
    token = os.environ.get("SMOKE_TOKEN", "smoke-token")
    monkeypatch.setenv("AUTH_SERVICE_TOKENS", token)
    tenant_id = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))
    monkeypatch.setenv("STORAGE_BACKEND", "file")
    base = settings.STORAGE_BASE_URI.replace("file://", "")
    Path(base).mkdir(parents=True, exist_ok=True)

    # Monkeypatch DNS resolution to a public IP for example.com
    monkeypatch.setattr(ingest_module, "_resolve_host_ips", lambda host: ["93.184.216.34"])  # example.com IP

    # Monkeypatch fetch to avoid real network
    pdf_bytes = b"%PDF-1.4\nHello"
    def fake_fetch(url: str):
        return pdf_bytes, "sample.pdf", "application/pdf", 5.0

    app = create_app()
    client = TestClient(app)

    # T-R1 Happy Path
    monkeypatch.setattr(ingest_module, "fetch_remote", fake_fetch)
    caplog.set_level("INFO")
    r1 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://example.com/sample.pdf", "source": "api"},
    )
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["status"] == "validated" and j1["duplicate"] is False
    inbox_id, content_hash = j1["id"], j1["content_hash"]
    assert _db_count("SELECT COUNT(*) FROM inbox_items WHERE tenant_id=:t AND content_hash=:h", {"t": tenant_id, "h": content_hash}) == 1
    assert _db_count(
        "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemValidated' AND payload_json::json->>'inbox_item_id'=:i",
        {"t": tenant_id, "i": inbox_id},
    ) == 1
    report["tests"].append({"name": "T-R1 Happy", "status": "passed"})

    # T-R2 Size Limit (set MAX_UPLOAD_MB=1 and return >1MB payload)
    old_limit = settings.MAX_UPLOAD_MB
    try:
        settings.MAX_UPLOAD_MB = 1
        big = b"%PDF-1.4\n" + (b"0" * (2 * 1024 * 1024))
        monkeypatch.setattr(ingest_module, "fetch_remote", lambda url: (big, "big.pdf", "application/pdf", 6.0))
        r2 = client.post(
            "/api/v1/inbox/items",
            headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
            json={"remote_url": "https://example.com/big.pdf"},
        )
        assert r2.status_code == 400 and r2.json()["detail"]["error"] == "size_limit"
        report["tests"].append({"name": "T-R2 Size", "status": "passed"})
    finally:
        settings.MAX_UPLOAD_MB = old_limit

    # T-R3 Scheme http://
    r3 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "http://example.com/a.pdf"},
    )
    assert r3.status_code == 400 and r3.json()["detail"]["error"] == "unsupported_scheme"
    report["tests"].append({"name": "T-R3 Scheme", "status": "passed"})

    # T-R4 Redirect limit (simulate through exception)
    class FakeRedirectErr(ingest_module.IngestError):
        pass

    def fake_redirect(url: str):
        raise ingest_module.IngestError("redirect_limit", 400, "Too many redirects")

    monkeypatch.setattr(ingest_module, "fetch_remote", fake_redirect)
    r4 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://example.com/redirect"},
    )
    assert r4.status_code == 400 and r4.json()["detail"]["error"] == "redirect_limit"
    report["tests"].append({"name": "T-R4 Redirect", "status": "passed"})

    # T-R5 Forbidden address (127.0.0.1)
    monkeypatch.setattr(ingest_module, "_resolve_host_ips", lambda host: ["127.0.0.1"])  # private/loopback
    r5 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://127.0.0.1/file.pdf"},
    )
    assert r5.status_code == 403 and r5.json()["detail"]["error"] == "forbidden_address"
    report["tests"].append({"name": "T-R5 Forbidden", "status": "passed"})

    # T-R6 Idempotency-Key
    monkeypatch.setattr(ingest_module, "_resolve_host_ips", lambda host: ["93.184.216.34"])  # restore public
    monkeypatch.setattr(ingest_module, "fetch_remote", fake_fetch)
    idem = "idem-xyz-1"
    r6a = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id, "Idempotency-Key": idem},
        json={"remote_url": "https://example.com/sample.pdf"},
    )
    r6b = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id, "Idempotency-Key": idem},
        json={"remote_url": "https://example.com/sample.pdf"},
    )
    assert r6a.status_code == 200 and r6b.status_code == 200
    j6a, j6b = r6a.json(), r6b.json()
    assert j6a["id"] == j6b["id"] and j6a["content_hash"] == j6b["content_hash"]
    assert _db_count("SELECT COUNT(*) FROM inbox_items WHERE tenant_id=:t AND content_hash=:h", {"t": tenant_id, "h": j6a["content_hash"]}) == 1
    assert _db_count(
        "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemValidated' AND idempotency_key=:k",
        {"t": tenant_id, "k": idem},
    ) == 1
    report["tests"].append({"name": "T-R6 Idem", "status": "passed"})

    # T-R7 MIME unsupported (random bytes)
    rnd = os.urandom(256)
    monkeypatch.setattr(ingest_module, "fetch_remote", lambda url: (rnd, "blob.bin", None, 3.0))
    r7 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://example.com/blob.bin"},
    )
    assert r7.status_code == 400 and r7.json()["detail"]["error"] == "unsupported_mime"
    report["tests"].append({"name": "T-R7 MIME", "status": "passed"})

    # Additional security edges (egress-free)
    # IPv6 loopback literal
    r8 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://[::1]/x.pdf"},
    )
    assert r8.status_code == 403 and r8.json()["detail"]["error"] == "forbidden_address"
    # Private IPv4 10.0.0.1
    monkeypatch.setattr(ingest_module, "_resolve_host_ips", lambda host: ["10.0.0.1"])
    r9 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://10.0.0.1/x.pdf"},
    )
    assert r9.status_code == 403 and r9.json()["detail"]["error"] == "forbidden_address"
    # ULA IPv6 fd00::
    r10 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://[fd00::1]/x.pdf"},
    )
    assert r10.status_code == 403 and r10.json()["detail"]["error"] == "forbidden_address"
    # IDNA/punycode domain (normalized)
    monkeypatch.setattr(ingest_module, "_resolve_host_ips", lambda host: ["93.184.216.34"])  # example.com-like
    monkeypatch.setattr(ingest_module, "fetch_remote", fake_fetch)
    r11 = client.post(
        "/api/v1/inbox/items",
        headers={"Authorization": f"Bearer {token}", "X-Tenant": tenant_id},
        json={"remote_url": "https://xn--exmple-cua.com/a.pdf"},
    )
    # Even if domain is nonsense, resolution is monkeypatched; ensure path goes through checks
    assert r11.status_code in (200, 400, 403)

    # Log assertions: remote URL should not appear in logs
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "http://" not in log_text and "https://" not in log_text
    assert "ingest_source" in log_text

    # Metrics include fetch_duration_ms histogram
    from backend.core.observability.metrics import get_metrics
    m = get_metrics()
    assert "fetch_duration_ms" in m

    REPORT_PATH.write_text(json.dumps(report, indent=2))
