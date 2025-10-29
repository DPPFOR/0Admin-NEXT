"""Tests for E-Invoice CLI generate/approve — auto-generated via PDD."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agents.einvoice.summary import mask_pii
from tools.einvoice.approve import approve_invoice
from tools.einvoice.export import export_invoice
from tools.einvoice.generate import _make_now_provider, generate_batch


def _fixed_factory(base: datetime):
    def factory() -> callable:
        return _make_now_provider(base)

    return factory


@pytest.mark.parametrize("format_name", ["facturx", "xrechnung"])
def test_generate_and_approve_flow(tmp_path: Path, format_name: str) -> None:
    tenant_id = "tenant-cli"
    base_now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    result = generate_batch(
        tenant_id=tenant_id,
        count=3,
        base_dir=tmp_path,
        now_provider_factory=_fixed_factory(base_now),
        format_name=format_name,
    )

    invoices = result["invoices"]
    assert len(invoices) == 3
    summary_path = result["summary_path"]
    assert summary_path is not None
    summary_file = Path(summary_path)
    assert summary_file.exists()
    summary_text = summary_file.read_text(encoding="utf-8")
    assert "Invoices verarbeitet" in summary_text
    # PII redaction check
    assert mask_pii("john.doe@example.com").endswith("@***")

    # Idempotenz
    repeat = generate_batch(
        tenant_id=tenant_id,
        count=3,
        base_dir=tmp_path,
        now_provider_factory=_fixed_factory(base_now),
        format_name=format_name,
    )
    assert [r["manifest_hash"] for r in invoices] == [r["manifest_hash"] for r in repeat["invoices"]]

    # Approve die ersten zwei Belege
    for entry in invoices[:2]:
        exported = approve_invoice(
            base_dir=tmp_path,
            tenant_id=tenant_id,
            invoice_no=entry["invoice_no"],
            format_name=format_name,
            actor="qa",
            comment="Looks good",
            now=base_now,
        )
        assert exported.exists()
        payload = exported.read_text(encoding="utf-8")
        assert "approved" in payload
        assert "qa" in payload

    # Artefaktverzeichnis vorhanden
    archive_suffix = "" if format_name == "facturx" else "-xrechnung"
    archive_dir = tmp_path / "artifacts" / "reports" / "einvoice" / tenant_id / f"{invoices[0]['invoice_no']}{archive_suffix}"
    assert archive_dir.exists()

    export_dest = tmp_path / "exports"
    exported_files = export_invoice(
        base_dir=tmp_path,
        dest_dir=export_dest,
        tenant_id=tenant_id,
        invoice_no=invoices[0]["invoice_no"],
        format_name=format_name,
        include_audit=True,
    )
    assert exported_files
    for file_path in exported_files:
        assert file_path.exists()

