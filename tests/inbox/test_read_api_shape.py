from __future__ import annotations

import os
from typing import Dict, Tuple

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


def _setup_database() -> Tuple[Dict[str, str], TestClient]:
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
        params={"tenant": ids["tenant"], "limit": 1, "offset": 0},
        headers={"X-Trace-ID": "trace-123"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Total-Count") == "1"
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert item["id"] == ids["accepted_invoice_id"]
    assert item["invoice_no"] == "INV-2025-0001"
    assert item["quality_status"] == "accepted"
    assert item["tenant_id"] == ids["tenant"]


def test_invoices_pagination_offset():
    ids, client = _setup_database()
    resp = client.get(
        "/inbox/read/invoices",
        params={"tenant": ids["tenant"], "limit": 1, "offset": 1},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == ids["review_invoice_id"]


def test_review_queue_endpoint():
    ids, client = _setup_database()
    resp = client.get("/inbox/read/review", params={"tenant": ids["tenant"]})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and data
    found = next((item for item in data if item["id"] == ids["review_invoice_id"]), None)
    assert found is not None
    assert found["quality_status"] == "needs_review"


def test_summary_endpoint():
    ids, client = _setup_database()
    resp = client.get("/inbox/read/summary", params={"tenant": ids["tenant"]})
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["tenant_id"] == ids["tenant"]
    assert summary["cnt_items"] == 2
    assert summary["cnt_invoices"] == 2
    assert summary["cnt_needing_review"] == 1
    assert summary["avg_confidence"] is not None


def test_tenant_required():
    _, client = _setup_database()
    resp = client.get("/inbox/read/invoices")
    assert resp.status_code == 422

    resp_invalid = client.get("/inbox/read/invoices", params={"tenant": "invalid"})
    assert resp_invalid.status_code == 422
