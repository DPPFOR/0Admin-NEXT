from __future__ import annotations

import argparse
import sys
from typing import Any, List, Optional
from uuid import UUID

from backend.clients.flock_reader.client import (
    FlockClientError,
    FlockReadClient,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoice triage playbook for Flock agents.")
    parser.add_argument("--tenant", required=True, help="Tenant UUID (required).")
    parser.add_argument("--base-url", default=None, help="Override the read API base URL.")
    return parser


def _validate_tenant(tenant: str) -> str:
    try:
        UUID(str(tenant))
    except (ValueError, TypeError) as exc:
        raise ValueError("tenant must be a valid UUID string") from exc
    return tenant


def _format_conf(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.1f}"
    except (ValueError, TypeError):
        return "n/a"


def _extract_items(payload: Any) -> List[dict]:
    if isinstance(payload, dict):
        items = payload.get("items", [])
        if isinstance(items, list):
            return items
        return []
    if isinstance(payload, list):
        return payload
    return []


def _extract_total(payload: Any, fallback_items: List[dict]) -> int:
    if isinstance(payload, dict):
        total = payload.get("total")
        if isinstance(total, int):
            return total
    return len(fallback_items)


def run_playbook(tenant: str, base_url: Optional[str] = None) -> int:
    tenant_id = _validate_tenant(tenant)
    client = FlockReadClient(base_url=base_url)

    try:
        accepted_payload = client.get_invoices(
            tenant_id,
            limit=50,
            offset=0,
            min_conf=80,
            status="accepted",
        )
        review_payload = client.get_review_queue(tenant_id, limit=50, offset=0)
    except (FlockClientError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    accepted_items = _extract_items(accepted_payload)
    review_items = _extract_items(review_payload)
    print(f"[triage] tenant={tenant_id}")
    print(
        f"[triage] accepted_count={_extract_total(accepted_payload, accepted_items)} "
        f"review_count={_extract_total(review_payload, review_items)}"
    )

    if not review_items:
        print("[triage] review queue empty")
        return 0

    sorted_review: List[dict] = sorted(
        review_items,
        key=lambda item: (item.get("confidence") or 0.0),
    )

    print("[triage] top_unsure:")
    for entry in sorted_review[:5]:
        doc_type = entry.get("doc_type") or entry.get("quality_status") or "unknown"
        confidence = _format_conf(entry.get("confidence"))
        identifier = entry.get("id") or entry.get("content_hash") or "n/a"
        quality = entry.get("quality_status") or "n/a"
        print(f" - {doc_type} id={identifier} status={quality} confidence={confidence}")

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
