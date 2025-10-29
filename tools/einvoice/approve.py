"""CLI zum Approven von E-Invoice Artefakten."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.einvoice.approval import approve


def _resolve_invoice_dir(base_dir: Path, tenant_id: str, invoice_no: str, format_name: str) -> tuple[Path, str]:
    suffix = "" if format_name == "facturx" else "-xrechnung"
    archive_invoice_no = f"{invoice_no}{suffix}"
    invoice_dir = base_dir / "artifacts" / "reports" / "einvoice" / tenant_id / archive_invoice_no
    return invoice_dir, archive_invoice_no


def approve_invoice(
    *,
    base_dir: Path,
    tenant_id: str,
    invoice_no: str,
    format_name: str = "facturx",
    actor: str = "system",
    comment: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Path:
    invoice_dir, archive_invoice_no = _resolve_invoice_dir(base_dir, tenant_id, invoice_no, format_name)
    if not invoice_dir.exists():
        raise FileNotFoundError(f"Invoice directory not found: {invoice_dir}")
    now = now or datetime.now(timezone.utc)
    return approve(invoice_dir, archive_invoice_no, now, actor=actor, comment=comment)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Approve E-Invoice artifacts")
    parser.add_argument("--tenant", required=True, help="Tenant ID (UUID)")
    parser.add_argument("--invoice-no", required=True, help="Invoice number without suffix")
    parser.add_argument("--format", choices=["facturx", "xrechnung"], default="facturx")
    parser.add_argument("--actor", default="system", help="Actor performing the approval")
    parser.add_argument("--comment", help="Optional approval comment")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Workspace root (default: cwd)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    path = approve_invoice(
        base_dir=args.base_dir,
        tenant_id=args.tenant,
        invoice_no=args.invoice_no,
        format_name=args.format,
        actor=args.actor,
        comment=args.comment,
    )
    print(f"Approval notice written to {path}")


if __name__ == "__main__":  # pragma: no cover
    main()

