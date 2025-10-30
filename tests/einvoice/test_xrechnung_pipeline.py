"""Tests for XRechnung pipeline — auto-generated via PDD."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import count
from pathlib import Path

import pytest

from agents.einvoice import (
    NumberingService,
    approve,
    build_sample_invoice,
    build_sample_profile,
    iter_sample_scenarios,
    write_package,
    xrechnung_version,
)
from agents.einvoice.xrechnung import build_xrechnung_document, validate_xrechnung


def _make_now_provider(start: datetime):
    ticker = count()

    def _next() -> datetime:
        return start + timedelta(seconds=next(ticker))

    return _next


def _run_pipeline(base_dir: Path, *, start: datetime) -> dict:
    now_provider = _make_now_provider(start)
    numbering = NumberingService(clock=now_provider)
    profile = build_sample_profile("tenant-x")

    previous_hash: str | None = None
    manifest_hashes: dict[str, str] = {}
    file_hashes: dict[str, dict[str, str]] = {}
    validation_flags: dict[str, dict[str, object]] = {}

    for scenario in iter_sample_scenarios():
        invoice_id = f"tenant-x-{scenario.code}"
        invoice = build_sample_invoice(
            scenario,
            invoice_id=invoice_id,
            tenant_id="tenant-x",
            issue_date=datetime(2025, 1, 1, tzinfo=timezone.utc).date(),
            due_date=datetime(2025, 1, 15, tzinfo=timezone.utc).date(),
            payment_terms=profile.payment_terms,
            now_provider=now_provider,
        )

        reservation_id = numbering.reserve("tenant-x", invoice.issue_date)
        invoice_no = numbering.commit(reservation_id)
        invoice.invoice_no = invoice_no

        xml_bytes = build_xrechnung_document(
            invoice,
            profile,
            now_provider(),
        )
        validation = validate_xrechnung(xml_bytes)
        assert validation.schema_ok, validation.messages
        assert validation.schematron_ok, validation.messages

        validation_bytes = json.dumps(
            validation.to_dict(), indent=2, sort_keys=True
        ).encode("utf-8")

        files = {
            "invoice.xml": xml_bytes,
            "validation.json": validation_bytes,
        }

        archive_invoice_no = f"{invoice_no}-xrechnung"
        package_dir, manifest_hash = write_package(
            base_dir,
            "tenant-x",
            archive_invoice_no,
            files,
            now=now_provider(),
            previous_hash=previous_hash,
            generator_version=xrechnung_version(),
        )
        approve(package_dir, archive_invoice_no, now=now_provider())

        manifest_hashes[archive_invoice_no] = manifest_hash
        file_hashes[archive_invoice_no] = {
            name: sha256(content).hexdigest() for name, content in files.items()
        }
        validation_flags[archive_invoice_no] = validation.to_dict()

        audit_files = list((package_dir / "audit").glob("NOTICE-*.json"))
        assert audit_files, "Audit notice missing"

        previous_hash = manifest_hash

    return {
        "manifest_hashes": manifest_hashes,
        "file_hashes": file_hashes,
        "validation_flags": validation_flags,
    }


@pytest.mark.parametrize(
    "start",
    [datetime(2025, 1, 1, tzinfo=timezone.utc)],
    ids=["baseline"],
)
def test_xrechnung_pipeline_is_idempotent(tmp_path: Path, start: datetime) -> None:
    first_run = _run_pipeline(tmp_path / "run1", start=start)
    second_run = _run_pipeline(tmp_path / "run2", start=start)

    assert first_run["manifest_hashes"] == second_run["manifest_hashes"]
    assert first_run["file_hashes"] == second_run["file_hashes"]

    for data in first_run["validation_flags"].values():
        assert data["schema_ok"] is True
        assert data["schematron_ok"] is True
        # Prüfe auf Validator-Marker (TEMP_VALIDATOR oder OFFICIAL_VALIDATOR)
        messages_str = " ".join(data.get("messages", []))
        assert "TEMP_VALIDATOR" in messages_str or "OFFICIAL_VALIDATOR" in messages_str

