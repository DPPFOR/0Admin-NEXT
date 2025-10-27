import json
import os
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from backend.app import create_app
from backend.core.config import settings

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL",
)

if not RUN_DB_TESTS:
    pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL", allow_module_level=True)


def _db_engine():
    return create_engine(os.environ.get("DATABASE_URL", settings.database_url), future=True)


def _db_exec(sql: str, params: dict = None):
    eng = _db_engine()
    with eng.begin() as conn:
        conn.execute(text(sql), params or {})


def _db_fetchval(sql: str, params: dict = None):
    eng = _db_engine()
    with eng.begin() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def test_read_ops_endpoints(monkeypatch, caplog):
    app = create_app()
    client = TestClient(app)
    caplog.set_level("INFO")

    # Seed data for two tenants
    t1 = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))
    t2 = str(uuid.uuid4())
    now = datetime.utcnow()

    def seed_inbox(tenant, idx):
        iid = str(uuid.uuid4())
        _db_exec(
            """
            INSERT INTO inbox_items (id, tenant_id, status, content_hash, uri, source, filename, mime, created_at)
            VALUES (:id, :t, 'validated', :ch, :uri, 'api', NULL, 'application/pdf', NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            {"id": iid, "t": tenant, "ch": f"hash{idx}", "uri": f"file:///tmp/{tenant}/{idx}.pdf"},
        )
        pid = str(uuid.uuid4())
        payload = json.dumps({"doc_type": "pdf", "invoice_no": f"INV-{idx}"})
        _db_exec(
            """
            INSERT INTO parsed_items (id, tenant_id, inbox_item_id, payload_json, created_at)
            VALUES (:id, :t, :iid, :p, NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            {"id": pid, "t": tenant, "iid": iid, "p": payload},
        )
        return iid, pid

    ids = [seed_inbox(t1, i) for i in range(5)]
    ids2 = [seed_inbox(t2, i) for i in range(3)]

    # Read inbox with keyset pagination
    xtrace = "trace-smoke-12345"
    r1 = client.get("/api/v1/inbox/items?limit=3", headers={"X-Tenant": t1, "X-Trace-ID": xtrace})
    assert r1.status_code == 200
    j1 = r1.json()
    assert len(j1["items"]) <= 3
    nxt = j1.get("next")
    if nxt:
        r2 = client.get(
            f"/api/v1/inbox/items?cursor={nxt}", headers={"X-Tenant": t1, "X-Trace-ID": xtrace}
        )
        assert r2.status_code == 200
        j2 = r2.json()
        # Disjoint pages (compare ids)
        ids_page1 = {x["id"] for x in j1["items"]}
        ids_page2 = {x["id"] for x in j2["items"]}
        assert ids_page1.isdisjoint(ids_page2)

    # Tenant isolation
    r3 = client.get("/api/v1/inbox/items", headers={"X-Tenant": t2, "X-Trace-ID": xtrace})
    assert r3.status_code == 200
    for it in r3.json()["items"]:
        assert it["tenant_id"] == t2

    # Parsed read whitelist
    rp = client.get("/api/v1/parsed/items", headers={"X-Tenant": t1, "X-Trace-ID": xtrace})
    assert rp.status_code == 200
    for it in rp.json()["items"]:
        assert set(it.keys()).issuperset({"id", "tenant_id", "inbox_item_id", "doc_type"})
        assert "filename" not in it
        assert "uri" not in it

    # Invalid cursor
    bad = client.get(
        "/api/v1/inbox/items?cursor=not-a-valid-cursor",
        headers={"X-Tenant": t1, "X-Trace-ID": xtrace},
    )
    assert bad.status_code == 400

    # Ops endpoints: require admin
    admin = os.environ.get("ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("ADMIN_TOKENS", admin)

    # Seed dead letter
    _db_exec(
        """
        INSERT INTO dead_letters (id, tenant_id, event_type, reason, payload_json, created_at)
        VALUES (:id, :t, 'InboxItemValidated', 'io_error', '{}', NOW())
        """,
        {"id": str(uuid.uuid4()), "t": t1},
    )

    dlq = client.get(
        "/api/v1/ops/dlq",
        headers={"Authorization": f"Bearer {admin}", "X-Tenant": t1, "X-Trace-ID": xtrace},
    )
    assert dlq.status_code == 200 and len(dlq.json()["items"]) >= 1

    # Dry run replay
    rep = client.post(
        "/api/v1/ops/dlq/replay",
        headers={"Authorization": f"Bearer {admin}", "X-Tenant": t1, "X-Trace-ID": xtrace},
        json={},
    )
    assert rep.status_code == 200 and rep.json()["committed"] == 0

    # Commit replay (limit 1)
    rep2 = client.post(
        "/api/v1/ops/dlq/replay",
        headers={"Authorization": f"Bearer {admin}", "X-Tenant": t1, "X-Trace-ID": xtrace},
        json={"dry_run": False, "limit": 1},
    )
    assert rep2.status_code == 200 and rep2.json()["committed"] == 1

    # Outbox status
    out = client.get(
        "/api/v1/ops/outbox",
        headers={"Authorization": f"Bearer {admin}", "X-Tenant": t1, "X-Trace-ID": xtrace},
    )
    assert out.status_code == 200

    # Metrics endpoint
    met = client.get(
        "/api/v1/ops/metrics", headers={"Authorization": f"Bearer {admin}", "X-Trace-ID": xtrace}
    )
    assert met.status_code == 200 and isinstance(met.json(), dict)

    # Log assertions: trace id propagated; token not logged in clear; only actor_token_hash appears
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert xtrace in log_text
    assert "actor_token_hash" in log_text
    assert admin not in log_text
    # PII negative list
    assert "@" not in log_text
    assert "filename=" not in log_text
    assert "file://" not in log_text
