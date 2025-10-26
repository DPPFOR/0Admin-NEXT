from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, Optional
from uuid import UUID

from backend.clients.flock_reader.client import (
    FlockClientError,
    FlockReadClient,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Payment recap playbook for Flock agents.")
    parser.add_argument("--tenant", required=True, help="Tenant UUID (required).")
    parser.add_argument("--base-url", default=None, help="Override the read API base URL.")
    return parser


def _validate_tenant(tenant: str) -> str:
    try:
        UUID(str(tenant))
    except (ValueError, TypeError) as exc:
        raise ValueError("tenant must be a valid UUID string") from exc
    return tenant


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_optional(value) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "n/a"


def _extract_items(payload: Any) -> list:
    if isinstance(payload, dict):
        items = payload.get("items", [])
        if isinstance(items, list):
            return items
        return []
    if isinstance(payload, list):
        return payload
    return []


def _extract_total(payload: Any, fallback: list) -> int:
    if isinstance(payload, dict):
        value = payload.get("total")
        if isinstance(value, int):
            return value
    return len(fallback)


def run_playbook(tenant: str, base_url: Optional[str] = None) -> int:
    tenant_id = _validate_tenant(tenant)
    client = FlockReadClient(base_url=base_url)

    try:
        payments_payload = client.get_payments(tenant_id, limit=100)
        summary = client.get_summary(tenant_id)
    except (FlockClientError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    payments = _extract_items(payments_payload)
    totals: Dict[str, float] = {}
    for payment in payments:
        payment_date = payment.get("payment_date")
        if not payment_date:
            continue
        month = str(payment_date)[:7]
        amount = _to_float(payment.get("amount"))
        totals[month] = totals.get(month, 0.0) + amount

    print(f"[recap] tenant={tenant_id}")
    print(f"[recap] payments_count={_extract_total(payments_payload, payments)}")
    print(f"[recap] avg_payment_confidence={_format_optional(summary.get('avg_confidence'))}")
    print(f"[recap] needing_review={summary.get('cnt_needing_review', 0)}")

    if not totals:
        print("[recap] no payment totals available")
        return 0

    print("[recap] monthly_totals:")
    for month in sorted(totals):
        print(f" - {month}: {totals[month]:.2f}")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_playbook(args.tenant, base_url=args.base_url)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
