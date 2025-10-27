import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL",
)


def test_tenant_policy_api(monkeypatch):
    app = create_app()
    client = TestClient(app)

    valid = os.environ.get("SMOKE_TENANT", "11111111-1111-1111-1111-111111111111")
    invalid = "99999999-9999-9999-9999-999999999999"
    monkeypatch.setenv("TENANT_ALLOWLIST", valid)

    # T-A1 valid
    r_ok = client.get("/api/v1/inbox/items", headers={"X-Tenant": valid})
    assert r_ok.status_code == 200

    # T-A2 missing
    r_miss = client.get("/api/v1/inbox/items")
    assert r_miss.status_code == 401 and r_miss.json()["detail"]["error"] == "tenant_missing"

    # T-A3 malformed
    r_malf = client.get("/api/v1/inbox/items", headers={"X-Tenant": "not-a-uuid"})
    assert r_malf.status_code == 401 and r_malf.json()["detail"]["error"] == "tenant_malformed"

    # T-A4 unknown
    r_unk = client.get("/api/v1/inbox/items", headers={"X-Tenant": invalid})
    assert r_unk.status_code == 403 and r_unk.json()["detail"]["error"] == "tenant_unknown"
