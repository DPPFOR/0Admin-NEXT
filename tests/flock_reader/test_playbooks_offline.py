from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.clients.flock_reader.client import FlockClientError
from tools.flock import playbook_invoice_triage, playbook_payment_recap

TENANT = "22222222-2222-2222-2222-222222222222"


class DummyInvoiceClient:
    def __init__(self, *, base_url=None):
        self.base_url = base_url
        self.invocation: Dict[str, Any] = {}

    def get_invoices(self, tenant_id, **params):
        self.invocation["invoices"] = (tenant_id, params)
        return {
            "items": [
                {"id": "acc-1", "tenant_id": tenant_id, "confidence": 0.95, "quality_status": "accepted"},
            ],
            "total": 1,
            "limit": params.get("limit", 50),
            "offset": params.get("offset", 0),
        }

    def get_review_queue(self, tenant_id, **params):
        self.invocation["review"] = (tenant_id, params)
        return {
            "items": [
                {"id": "rev-1", "tenant_id": tenant_id, "confidence": 0.42, "doc_type": "invoice", "quality_status": "needs_review"},
                {"id": "rev-2", "tenant_id": tenant_id, "confidence": 0.12, "doc_type": "other", "quality_status": "rejected"},
                {"id": "rev-3", "tenant_id": tenant_id, "confidence": 0.66, "doc_type": "invoice", "quality_status": "needs_review"},
            ],
            "total": 3,
            "limit": params.get("limit", 50),
            "offset": params.get("offset", 0),
        }


def test_invoice_triage_happy_path(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    dummy = DummyInvoiceClient()
    monkeypatch.setattr("tools.flock.playbook_invoice_triage.FlockReadClient", lambda base_url=None: dummy)

    exit_code = playbook_invoice_triage.main(["--tenant", TENANT, "--base-url", "http://api.local"])
    captured = capfd.readouterr()

    assert exit_code == 0
    assert "[triage] tenant=" in captured.out
    assert "top_unsure" in captured.out

    tenant_call, params = dummy.invocation["invoices"]
    assert tenant_call == TENANT
    assert params["status"] == "accepted"
    assert params["min_conf"] == 80


def test_invoice_triage_handles_client_error(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    class FailingClient:
        def __init__(self, *, base_url=None):
            pass

        def get_invoices(self, *args, **kwargs):
            raise FlockClientError("boom")

        def get_review_queue(self, *args, **kwargs):
            return []

    monkeypatch.setattr("tools.flock.playbook_invoice_triage.FlockReadClient", FailingClient)
    exit_code = playbook_invoice_triage.main(["--tenant", TENANT])
    captured = capfd.readouterr()

    assert exit_code == 2
    assert "boom" in captured.err


class DummyPaymentClient:
    def __init__(self, *, base_url=None):
        self.base_url = base_url

    def get_payments(self, tenant_id, **params):
        return {
            "items": [
                {"id": "pay-1", "tenant_id": tenant_id, "amount": 100, "payment_date": "2025-01-15"},
                {"id": "pay-2", "tenant_id": tenant_id, "amount": 50, "payment_date": "2025-01-05"},
                {"id": "pay-3", "tenant_id": tenant_id, "amount": 75, "payment_date": "2025-02-01"},
            ],
            "total": 3,
            "limit": params.get("limit", 100),
            "offset": params.get("offset", 0),
        }

    def get_summary(self, tenant_id):
        return {"tenant_id": tenant_id, "avg_confidence": 0.85, "cnt_needing_review": 2}


def test_payment_recap_prints_totals(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    dummy = DummyPaymentClient()
    monkeypatch.setattr("tools.flock.playbook_payment_recap.FlockReadClient", lambda base_url=None: dummy)

    exit_code = playbook_payment_recap.main(["--tenant", TENANT])
    captured = capfd.readouterr()

    assert exit_code == 0
    assert "monthly_totals" in captured.out
    assert "2025-01" in captured.out
    assert "150.00" in captured.out


def test_payment_recap_invalid_tenant(capfd: pytest.CaptureFixture[str]) -> None:
    exit_code = playbook_payment_recap.main(["--tenant", "not-a-uuid"])
    captured = capfd.readouterr()

    assert exit_code == 2
    assert "valid UUID" in captured.err
