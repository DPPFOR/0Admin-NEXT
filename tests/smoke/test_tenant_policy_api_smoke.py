import os
import uuid

import pytest
from fastapi.testclient import TestClient

try:
    from backend.app import create_app
except ModuleNotFoundError as exc:
    pytest.skip(f"backend package not importable: {exc}", allow_module_level=True)

RUN_API_SMOKES = os.getenv("RUN_API_SMOKES") == "1"

if not RUN_API_SMOKES:
    pytest.skip("requires RUN_API_SMOKES=1 and full backend stack", allow_module_level=True)


def test_tenant_policy_api(monkeypatch):
    app = create_app()
    client = TestClient(app)

    valid = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))
    invalid = str(uuid.uuid4())
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
