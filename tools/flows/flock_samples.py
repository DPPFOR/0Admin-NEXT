#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


def _http_get(url: str, *, timeout: float = 5.0, retries: int = 1) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # type: ignore[no-redef]
                payload = resp.read().decode("utf-8")
                return json.loads(payload)
        except Exception as exc:  # pragma: no cover - network guard
            last_error = exc
            if attempt == retries:
                raise
            time.sleep(0.5)
    raise RuntimeError(last_error or "unexpected network failure")  # pragma: no cover


def fetch_invoices(tenant: str, base_url: str = "http://localhost:8000") -> Dict[str, Any]:
    query = urllib.parse.urlencode({"tenant": tenant, "limit": 5, "offset": 0})
    url = f"{base_url.rstrip('/')}/inbox/read/invoices?{query}"
    return _http_get(url)


def fetch_review_queue(tenant: str, base_url: str = "http://localhost:8000") -> Dict[str, Any]:
    query = urllib.parse.urlencode({"tenant": tenant, "limit": 5, "offset": 0})
    url = f"{base_url.rstrip('/')}/inbox/read/review?{query}"
    return _http_get(url)


def _print_preview(label: str, data: Any) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    lines = text.splitlines()
    preview = "\n".join(lines[:3])
    print(f"{label}:\n{preview}")
    if len(lines) > 3:
        print("... (truncated)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample Flock consumer for inbox read-model API")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Inbox API base URL")
    parser.add_argument(
        "--what",
        choices=("invoices", "review", "both"),
        default="both",
        help="Which datasets to fetch",
    )
    args = parser.parse_args(argv)

    try:
        if args.what in ("invoices", "both"):
            invoices = fetch_invoices(args.tenant, base_url=args.base_url)
            _print_preview("invoices", invoices)
        if args.what in ("review", "both"):
            review = fetch_review_queue(args.tenant, base_url=args.base_url)
            _print_preview("review", review)
    except Exception as exc:  # pragma: no cover - network guard
        print(f"error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
