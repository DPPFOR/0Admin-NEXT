#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.apps.inbox.read_model.query import (
    ReadModelError,
    fetch_invoices_latest,
    fetch_items_needing_review,
    fetch_payments_latest,
    fetch_tenant_summary,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _coerce_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "hex") and hasattr(value, "bytes"):  # UUID
        return str(value)
    return value


def _dto_to_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        data = {key: _dto_to_dict(val) for key, val in asdict(obj).items()}
        return data
    if isinstance(obj, list):
        return [_dto_to_dict(item) for item in obj]
    return _coerce_value(obj)


def _print_pretty_sequence(items: Iterable[dict[str, Any]]) -> None:
    for idx, item in enumerate(items, start=1):
        print(f"# {idx}")
        for key, val in item.items():
            print(f"{key}: {val}")
        print()


def _print_pretty_single(item: dict[str, Any]) -> None:
    for key, val in item.items():
        print(f"{key}: {val}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query inbox read-model views (read-only)")
    parser.add_argument("--tenant", required=True, help="Tenant UUID to filter on")
    parser.add_argument(
        "--what",
        required=True,
        choices=("invoices", "payments", "review", "summary"),
        help="Query target",
    )
    parser.add_argument("--limit", type=int, default=50, help="Pagination limit for list queries")
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset for list queries")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    try:
        if args.what == "invoices":
            items = fetch_invoices_latest(args.tenant, limit=args.limit, offset=args.offset)
        elif args.what == "payments":
            items = fetch_payments_latest(args.tenant, limit=args.limit, offset=args.offset)
        elif args.what == "review":
            items = fetch_items_needing_review(args.tenant, limit=args.limit, offset=args.offset)
        else:
            items = fetch_tenant_summary(args.tenant)
    except (ValueError, ReadModelError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover
        print(str(exc), file=sys.stderr)
        return 3

    payload = _dto_to_dict(items)

    if args.as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if isinstance(payload, list):
        _print_pretty_sequence(payload)
    elif payload is None:
        print("No data")
    else:
        _print_pretty_single(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
