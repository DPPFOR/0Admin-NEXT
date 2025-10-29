"""CLI zum Exportieren von E-Invoice Artefakten auf das Dateisystem."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List


def _resolve_invoice_dir(base_dir: Path, tenant_id: str, invoice_no: str, format_name: str) -> tuple[Path, str]:
    suffix = "" if format_name == "facturx" else "-xrechnung"
    archive_invoice_no = f"{invoice_no}{suffix}"
    invoice_dir = base_dir / "artifacts" / "reports" / "einvoice" / tenant_id / archive_invoice_no
    return invoice_dir, archive_invoice_no


def export_invoice(
    *,
    base_dir: Path,
    dest_dir: Path,
    tenant_id: str,
    invoice_no: str,
    format_name: str = "facturx",
    include_audit: bool = False,
) -> List[Path]:
    invoice_dir, archive_invoice_no = _resolve_invoice_dir(base_dir, tenant_id, invoice_no, format_name)
    if not invoice_dir.exists():
        raise FileNotFoundError(f"Invoice directory not found: {invoice_dir}")

    dest = dest_dir / archive_invoice_no
    dest.mkdir(parents=True, exist_ok=True)

    copied: List[Path] = []
    for candidate in ["invoice.pdf", "invoice.xml", "validation.json", "manifest.json"]:
        src = invoice_dir / candidate
        if src.exists() and src.is_file():
            target = dest / candidate
            shutil.copy2(src, target)
            copied.append(target)

    if include_audit:
        audit_src = invoice_dir / "audit"
        if audit_src.exists() and audit_src.is_dir():
            audit_dest = dest / "audit"
            if audit_dest.exists():
                shutil.rmtree(audit_dest)
            shutil.copytree(audit_src, audit_dest)
            copied.append(audit_dest)

    metadata = dest / "export_metadata.txt"
    metadata.write_text(
        f"tenant={tenant_id}\ninvoice={archive_invoice_no}\nformat={format_name}\nexported_at={datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}\n",
        encoding="utf-8",
    )
    copied.append(metadata)
    return copied


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export E-Invoice artifacts to a destination directory")
    parser.add_argument("--tenant", required=True, help="Tenant ID (UUID)")
    parser.add_argument("--invoice-no", required=True, help="Invoice number without suffix")
    parser.add_argument("--dest", required=True, type=Path, help="Export destination directory")
    parser.add_argument("--format", choices=["facturx", "xrechnung"], default="facturx")
    parser.add_argument("--include-audit", action="store_true", help="Include audit notices in export")
    parser.add_argument("--mail-stub", action="store_true", help="(Stub) trigger mail export – noop")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Workspace root (default: cwd)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    copied = export_invoice(
        base_dir=args.base_dir,
        dest_dir=args.dest,
        tenant_id=args.tenant,
        invoice_no=args.invoice_no,
        format_name=args.format,
        include_audit=args.include_audit,
    )
    if args.mail_stub:
        print("Mail export stub is disabled – skipping.")
    print("Exported artifacts:")
    for path in copied:
        print(f" - {path}")


if __name__ == "__main__":  # pragma: no cover
    main()

