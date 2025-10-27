from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.apps.inbox.importer.validators import other_DoD, payment_DoD


def test_payment_dod_accepts_complete_payload():
    confidence, rules, status = payment_DoD(
        amount=Decimal("150.00"),
        currency="eur",
        payment_date=date(2025, 2, 15),
        counterparty="ACME Bank",
    )

    assert confidence == Decimal("100.00")
    assert status == "accepted"
    assert rules == []


def test_payment_dod_rejects_missing_fields():
    confidence, rules, status = payment_DoD(
        amount=None,
        currency="zzz",
        payment_date=None,
        counterparty="",
    )

    assert status == "rejected"
    assert confidence == Decimal("70.00")  # baseline score without bonuses
    error_codes = {rule["code"] for rule in rules}
    assert "payment.amount.invalid" in error_codes
    assert "payment.currency.unsupported" in error_codes
    assert "payment.date.missing" in error_codes
    assert "payment.counterparty.missing" in error_codes


def test_other_dod_accepts_structured_payload():
    tables = [{"headers": ["column"], "rows": [["value"]]}]
    kv_entries = [{"key": "Subject", "value": "Notice"}, {"key": "Reference", "value": "REF-1"}]

    confidence, rules, status = other_DoD(kv_entries=kv_entries, tables=tables)

    assert status == "accepted"
    assert confidence == Decimal("60.00")
    assert all(rule["level"] == "warning" for rule in rules)


def test_other_dod_rejects_empty_payload():
    confidence, rules, status = other_DoD(kv_entries=[], tables=[])

    assert status == "rejected"
    assert any(rule["code"] == "other.structure.empty" for rule in rules)
    assert confidence == Decimal("40.00")
