"""Tests for Factur-X pipeline — auto-generated via PDD."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import count
from pathlib import Path

import pytest

from agents.einvoice import (
    NumberingService,
    build_facturx_document,
    build_sample_invoice,
    build_sample_profile,
    iter_sample_scenarios,
    validate_facturx,
    version,
    write_package,
)
from agents.einvoice.approval import approve


def _make_now_provider(start: datetime):
    ticker = count()

    def _next() -> datetime:
        return start + timedelta(seconds=next(ticker))

    return _next


def _run_pipeline(base_dir: Path, *, start: datetime) -> dict:
    now_provider = _make_now_provider(start)
    numbering = NumberingService(clock=now_provider)
    profile = build_sample_profile("tenant-a")

    previous_hash: str | None = None
    manifest_hashes = {}
    file_hashes = {}
    validation_flags = {}

    for scenario in iter_sample_scenarios():
        invoice_id = f"tenant-a-{scenario.code}"
        invoice = build_sample_invoice(
            scenario,
            invoice_id=invoice_id,
            tenant_id="tenant-a",
            issue_date=datetime(2025, 1, 1, tzinfo=timezone.utc).date(),
            due_date=datetime(2025, 1, 15, tzinfo=timezone.utc).date(),
            payment_terms=profile.payment_terms,
            now_provider=now_provider,
        )
        reservation_id = numbering.reserve("tenant-a", invoice.issue_date)
        invoice_no = numbering.commit(reservation_id)
        invoice.invoice_no = invoice_no

        document_ts = now_provider()
        pdf_bytes, xml_bytes = build_facturx_document(invoice, profile, document_ts)
        validation = validate_facturx(xml_bytes)
        assert validation.schema_ok
        assert validation.schematron_ok

        validation_bytes = json.dumps(
            validation.to_dict(), indent=2, sort_keys=True
        ).encode("utf-8")
        files = {
            "invoice.pdf": pdf_bytes,
            "invoice.xml": xml_bytes,
            "validation.json": validation_bytes,
        }

        package_dir, manifest_hash = write_package(
            base_dir,
            "tenant-a",
            invoice_no,
            files,
            now=now_provider(),
            previous_hash=previous_hash,
            generator_version=version(),
        )
        approve(package_dir, invoice_no, now=now_provider())

        manifest_hashes[invoice_no] = manifest_hash
        file_hashes[invoice_no] = {
            name: sha256(content).hexdigest() for name, content in files.items()
        }
        validation_flags[invoice_no] = json.loads(
            (package_dir / "validation.json").read_text(encoding="utf-8")
        )

        audit_files = list((package_dir / "audit").glob("NOTICE-*"))
        assert audit_files, "Audit notice missing"

        previous_hash = manifest_hash

    return {
        "manifest_hashes": manifest_hashes,
        "file_hashes": file_hashes,
        "validation_flags": validation_flags,
    }


@pytest.mark.parametrize(
    "start",
    [datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)],
    ids=["baseline"],
)
def test_facturx_pipeline_is_idempotent(tmp_path: Path, start: datetime) -> None:
    first_run = _run_pipeline(tmp_path / "run1", start=start)
    second_run = _run_pipeline(tmp_path / "run2", start=start)

    assert first_run["manifest_hashes"] == second_run["manifest_hashes"]
    assert first_run["file_hashes"] == second_run["file_hashes"]

    for invoice_no, validation in first_run["validation_flags"].items():
        assert validation["schema_ok"] is True
        assert validation["schematron_ok"] is True
        assert "TEMP_VALIDATOR" in " ".join(validation.get("messages", []))

