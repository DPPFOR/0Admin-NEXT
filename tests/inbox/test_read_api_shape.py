from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.app import create_app
from tests.inbox.test_read_model_db import (
    TENANT_ID,
    _ensure_database_ready,
    _reset_tenant,
    _seed_data,
)

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL")


def _setup_database() -> tuple[dict[str, str], TestClient]:
    if not RUN_DB_TESTS or not DB_URL:
        pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL")
    engine = create_engine(DB_URL, future=True)
    _ensure_database_ready(engine)
    _reset_tenant(engine, TENANT_ID)
    ids = _seed_data(engine)
    app = create_app()
    client = TestClient(app)
    return ids, client


def test_invoices_endpoint_success():
    ids, client = _setup_database()
    response = client.get(
        "/inbox/read/invoices",
        params={"limit": 1, "offset": 0},
        headers={"X-Tenant-ID": ids["tenant"], "X-Trace-ID": "trace-123"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Total-Count") == "1"
    data = response.json()
    assert isinstance(data, dict)
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert data["total"] == 1
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == ids["accepted_invoice_id"]
    assert item["invoice_no"] == "INV-2025-0001"
    assert item["quality_status"] == "accepted"
    assert item["tenant_id"] == ids["tenant"]
    assert "flags" in item and isinstance(item["flags"], dict)
    assert item.get("mvr_preview") is False
    assert item.get("mvr_score") in (None, 0, 0.0)


def test_invoices_pagination_offset():
    ids, client = _setup_database()
    resp = client.get(
        "/inbox/read/invoices",
        params={"limit": 1, "offset": 1},
        headers={"X-Tenant-ID": ids["tenant"]},
    )
    assert resp.status_code == 200
    payload = resp.json()
    items = payload["items"]
    assert len(items) == 1
    assert items[0]["id"] == ids["review_invoice_id"]


def test_review_queue_endpoint():
    ids, client = _setup_database()
    resp = client.get("/inbox/read/review", headers={"X-Tenant-ID": ids["tenant"]})
    assert resp.status_code == 200
    payload = resp.json()
    data = payload["items"]
    assert isinstance(data, list) and data
    found = next((item for item in data if item["id"] == ids["review_invoice_id"]), None)
    assert found is not None
    assert found["quality_status"] == "needs_review"
    assert "flags" in found
    assert any(item["doc_type"] == "other" for item in data)


def test_payments_endpoint():
    ids, client = _setup_database()
    response = client.get(
        "/inbox/read/payments",
        params={"limit": 5, "offset": 0},
        headers={"X-Tenant-ID": ids["tenant"]},
    )
    assert response.status_code == 200
    payload = response.json()
    items = payload["items"]
    assert isinstance(items, list) and items
    payment = next((item for item in items if item["content_hash"] == "payment-good-0001"), None)
    assert payment is not None
    assert payment["counterparty"] == "ACME Bank"
    assert payment["currency"] == "EUR"
    assert payment["quality_status"] == "accepted"
    assert payment.get("mvr_preview") in {True, False}
    assert "flags" in payment


def test_summary_endpoint():
    ids, client = _setup_database()
    resp = client.get("/inbox/read/summary", headers={"X-Tenant-ID": ids["tenant"]})
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["tenant_id"] == ids["tenant"]
    assert summary["cnt_items"] == 4
    assert summary["cnt_invoices"] == 2
    assert summary["cnt_payments"] == 1
    assert summary["cnt_other"] == 1
    assert summary["cnt_needing_review"] == 2
    assert summary["cnt_mvr_preview"] >= 1
    assert summary["avg_confidence"] is not None
    assert "avg_mvr_score" in summary


def test_tenant_required():
    _, client = _setup_database()
    resp = client.get("/inbox/read/invoices")
    assert resp.status_code == 422

    resp_invalid = client.get("/inbox/read/invoices", headers={"X-Tenant-ID": "invalid"})
    assert resp_invalid.status_code == 422


def test_invoices_filters_apply():
    ids, client = _setup_database()
    resp = client.get(
        "/inbox/read/invoices",
        params={"status": "accepted", "min_conf": 90},
        headers={"X-Tenant-ID": ids["tenant"]},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert all(item["quality_status"] == "accepted" for item in payload["items"])

    low_resp = client.get(
        "/inbox/read/invoices",
        params={"status": "needs_review", "min_conf": 50},
        headers={"X-Tenant-ID": ids["tenant"]},
    )
    assert low_resp.status_code == 200
    low_payload = low_resp.json()
    assert low_payload["total"] == 0


def test_multi_tenant_isolation():
    ids, client = _setup_database()
    other_tenant = "00000000-0000-0000-0000-000000000002"
    resp = client.get("/inbox/read/invoices", headers={"X-Tenant-ID": other_tenant})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 0

    summary_resp = client.get("/inbox/read/summary", headers={"X-Tenant-ID": other_tenant})
    assert summary_resp.status_code == 404
