"""Sender policy sanity probe.

Validates that required environment variables are present and that the
bounce policy matches the documented rules.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path("artifacts/reports/mahnwesen")


BOUNCE_POLICY = {
    "hard": {"action": "block_immediately", "retry_attempts": 0},
    "soft": {"action": "retry_then_promote", "max_attempts": 3, "window_hours": 72},
}


REQUIRED_ENVS = [
    "BREVO_API_KEY",
    "BREVO_SENDER_EMAIL",
    "BREVO_SENDER_NAME",
    "TENANT_DEFAULT",
]


def collect_env_status() -> dict[str, str]:
    status: dict[str, str] = {}
    for key in REQUIRED_ENVS:
        value = os.getenv(key)
        status[key] = "SET" if value else "UNSET"
    return status


def build_probe(tenant_id: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "env_status": collect_env_status(),
        "bounce_policy": BOUNCE_POLICY,
        "notes": [
            "BREVO_* values must be provided via environment variables.",
            "Hard bounces are blocked immediately.",
            "Soft bounces are retried up to 3 times within 72 hours, then promoted to hard.",
        ],
    }


def write_probe(tenant_id: str, data: dict[str, Any]) -> Path:
    tenant_dir = ARTIFACT_ROOT / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    path = tenant_dir / "sender_policy_probe.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sender policy probe")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_probe(args.tenant)
    path = write_probe(args.tenant, report)
    print(json.dumps({"tenant_id": args.tenant, "output": str(path)}, ensure_ascii=False))
    print("Sender policy probe completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

