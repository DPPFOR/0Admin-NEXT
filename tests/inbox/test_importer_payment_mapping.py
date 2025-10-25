from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from backend.apps.inbox.importer.mapper import artifact_to_dtos

SAMPLES_DIR = Path("artifacts/inbox_local/samples")
TENANT = "00000000-0000-0000-0000-000000000001"


def _load_sample(name: str) -> dict:
    with open(SAMPLES_DIR / name, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["tenant_id"] == TENANT
    return data


def test_payment_mapping_sets_payment_doctype_and_metadata():
    data = _load_sample("payment_good.json")
    item, chunks = artifact_to_dtos(
        data,
        enforce_invoice=False,
        enforce_payment=True,
        enforce_other=True,
    )

    assert item.doctype == "payment"
    assert item.quality_status == "accepted"
    assert item.amount == Decimal("250.00")
    assert item.due_date.isoformat() == "2025-02-15"
    payment_payload = item.payload["extracted"]["payment"]
    assert payment_payload["currency"] == "EUR"
    assert payment_payload["counterparty"] == "ACME Bank"
    assert any(chunk.kind == "kv" for chunk in chunks)
    assert item.flags.get("enable_table_boost") is True
    assert item.flags.get("mvr_preview") is True
    assert item.mvr_preview is True
    assert item.mvr_score == Decimal("0.00")


def test_payment_mapping_rejected_for_invalid_payload():
    data = _load_sample("payment_bad.json")
    item, _ = artifact_to_dtos(
        data,
        enforce_invoice=False,
        enforce_payment=True,
        enforce_other=True,
    )

    assert item.doctype == "payment"
    assert item.quality_status == "rejected"
    rule_codes = {rule["code"] for rule in item.rules}
    assert "payment.amount.invalid" in rule_codes
    assert item.flags.get("enable_ocr") is False


def test_other_mapping_triggered_when_invoice_requirements_fail():
    data = _load_sample("other_min.json")
    item, chunks = artifact_to_dtos(
        data,
        enforce_invoice=False,
        enforce_payment=True,
        enforce_other=True,
    )

    assert item.doctype == "other"
    assert item.quality_status in {"accepted", "needs_review"}
    assert any(chunk.kind == "kv" for chunk in chunks)
    assert "mvr_preview" in item.flags
