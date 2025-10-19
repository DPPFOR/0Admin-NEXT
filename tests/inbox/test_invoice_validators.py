from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import importlib.util as _iu


def _load_validators():
    spec = _iu.spec_from_file_location("validators", "backend/apps/inbox/importer/validators.py")
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


v = _load_validators()


def _has_code(rules: list[dict[str, str]], code: str) -> bool:
    return any(rule["code"] == code for rule in rules)


def test_validate_invoice_amount_rules():
    missing = v.validate_invoice_amount(None)
    assert _has_code(missing, "invoice.amount.missing")

    non_positive = v.validate_invoice_amount(Decimal("0"))
    assert _has_code(non_positive, "invoice.amount.invalid")

    ok = v.validate_invoice_amount(Decimal("10.50"))
    assert ok == []


def test_validate_invoice_due_date_rules():
    missing = v.validate_invoice_due_date(None)
    assert _has_code(missing, "invoice.due_date.missing")

    old_date = date.today() - timedelta(days=366)
    implausible = v.validate_invoice_due_date(old_date)
    assert _has_code(implausible, "invoice.due_date.implausible")
    warning = next(rule for rule in implausible if rule["code"] == "invoice.due_date.implausible")
    assert warning["level"] == "warning"

    ok = v.validate_invoice_due_date(date.today())
    assert ok == []


def test_validate_invoice_no_rules():
    missing = v.validate_invoice_no("")
    assert _has_code(missing, "invoice.number.missing")

    invalid = v.validate_invoice_no("!!bad")
    assert _has_code(invalid, "invoice.number.invalid")

    ok = v.validate_invoice_no("INV-1234")
    assert ok == []


def test_validate_table_shape_rules():
    good_table = {"headers": ["item", "price"], "rows": [["a", "10"], ["b", "12"]]}
    assert v.validate_table_shape(good_table) == []

    bad_columns = v.validate_table_shape({"headers": ["only"], "rows": [[]]})
    assert _has_code(bad_columns, "invoice.table.columns_missing")

    blank_header = v.validate_table_shape({"headers": ["", "price"], "rows": [["a", "1"]]})
    assert _has_code(blank_header, "invoice.table.header_blank")

    too_many_rows = v.validate_table_shape(
        {"headers": ["item", "price"], "rows": [["x", "1"]] * 5001}
    )
    assert _has_code(too_many_rows, "invoice.table.too_many_rows")


def test_confidence_and_quality_status_thresholds():
    assert v.compute_confidence(
        {"required_ok": True, "table_ok": True, "plausibility_ok": True, "source_ok": True}
    ) == 100

    assert v.compute_confidence(
        {"required_ok": True, "table_ok": False, "plausibility_ok": False, "source_ok": False}
    ) == 40

    assert v.decide_quality_status(True, 70) == "accepted"
    assert v.decide_quality_status(True, 69) == "needs_review"
    assert v.decide_quality_status(False, 50) == "needs_review"
    assert v.decide_quality_status(False, 49) == "rejected"
