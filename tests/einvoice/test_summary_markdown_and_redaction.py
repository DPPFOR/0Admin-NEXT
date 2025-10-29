"""Tests for E-Invoice summary and PII redaction — auto-generated via PDD."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agents.einvoice.summary import (
    InvoiceResult,
    RunSummary,
    build_summary_md,
    mask_pii,
    write_summary_markdown,
)


def test_mask_pii_covers_email_iban_phone() -> None:
    sample = "Contact john.doe@example.com / IBAN DE89370400440532013000 / Phone +49 170 1234567"
    masked = mask_pii(sample)
    assert "example.com" not in masked
    assert "IBAN-***" in masked
    assert "***-PHONE-***" in masked


def test_summary_markdown_written(tmp_path: Path) -> None:
    summary = RunSummary(
        tenant_id="tenant-test",
        format="facturx",
        generator_version="stub-1",
        created_at=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        results=[
            InvoiceResult(
                invoice_no="INV-2025-00001",
                format="facturx",
                manifest_hash="abc123",
                validation_ok=True,
                idempotency_key="tenant-test|INV-2025-00001|facturx",
            ),
            InvoiceResult(
                invoice_no="INV-2025-00002",
                format="facturx",
                manifest_hash="def456",
                validation_ok=False,
                idempotency_key="tenant-test|INV-2025-00002|facturx",
            ),
        ],
    )

    markdown = build_summary_md(summary)
    assert "Invoices verarbeitet: 2" in markdown
    path = write_summary_markdown(summary, tmp_path)
    assert path.exists()
    saved = path.read_text(encoding="utf-8")
    assert "INV-2025-00001" in saved
    assert "Manifest SHA256" in saved

