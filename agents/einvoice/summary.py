"""Hilfsfunktionen für E-Invoice Summary-Markdown und PII-Redaction."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List


MASK_EMAIL = re.compile(r"(?P<prefix>[A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*@(?P<domain>[A-Za-z0-9.-]+)")
MASK_IBAN = re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4,30}\b")
MASK_PHONE = re.compile(r"(?<![A-Za-z0-9\-])\+?\d[\d\s\-]{7,}\d")


def mask_pii(text: str) -> str:
    """Maskiert gängige PII-Muster (E-Mail, IBAN, Telefonnummer)."""

    text = MASK_EMAIL.sub(lambda m: f"{m.group('prefix')}***@***", text)
    text = MASK_IBAN.sub("IBAN-***", text)
    text = MASK_PHONE.sub("***-PHONE-***", text)
    return text


@dataclass(slots=True)
class InvoiceResult:
    invoice_no: str
    format: str
    manifest_hash: str
    validation_ok: bool
    idempotency_key: str


@dataclass(slots=True)
class RunSummary:
    tenant_id: str
    format: str
    generator_version: str
    created_at: datetime
    results: List[InvoiceResult]

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.validation_ok)

    @property
    def failure_count(self) -> int:
        return len(self.results) - self.success_count

    @property
    def total_count(self) -> int:
        return len(self.results)


def build_summary_md(summary: RunSummary) -> str:
    header = (
        f"E-Invoice Summary\n"
        f"===================\n\n"
        f"Tenant: `{summary.tenant_id}`\n"
        f"Format: `{summary.format}`\n"
        f"Generator-Version: `{summary.generator_version}`\n"
        f"Zeitstempel (UTC): `{summary.created_at.isoformat().replace('+00:00', 'Z')}`\n"
        f"Invoices verarbeitet: {summary.total_count}\n"
        f"Erfolgreich: {summary.success_count} | Fehlgeschlagen: {summary.failure_count}\n\n"
    )

    lines = [header, "## Details\n"]
    for result in summary.results:
        item = (
            f"- `{result.invoice_no}` [{result.format}] - "
            f"Manifest SHA256: `{result.manifest_hash}` - "
            f"Validation: {'OK' if result.validation_ok else 'FAILED'} - "
            f"Idempotency-Key: `{hashlib.sha256(result.idempotency_key.encode()).hexdigest()}`"
        )
        lines.append(item)
    lines.append("")
    markdown = "\n".join(lines)
    return mask_pii(markdown)


def write_summary_markdown(summary: RunSummary, base_dir: Path) -> Path:
    summary_dir = base_dir / "artifacts" / "reports" / "einvoice" / summary.tenant_id
    summary_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{summary.created_at.date().isoformat()}_summary.md"
    target = summary_dir / filename
    target.write_text(build_summary_md(summary), encoding="utf-8")
    return target


def collect_results(raw_results: Iterable[dict]) -> List[InvoiceResult]:
    results: List[InvoiceResult] = []
    for entry in raw_results:
        results.append(
            InvoiceResult(
                invoice_no=entry["invoice_no"],
                format=entry["format"],
                manifest_hash=entry["manifest_hash"],
                validation_ok=entry.get("validation", {}).get("schema_ok", True)
                and entry.get("validation", {}).get("schematron_ok", True),
                idempotency_key=entry["idempotency_key"],
            )
        )
    return results

