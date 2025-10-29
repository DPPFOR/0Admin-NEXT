"""Manage Mahnwesen operate kill switch state for backout."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict


def apply_kill_switch(
    *,
    tenant_id: str,
    reason: str,
    trace_id: str,
    state_dir: Path | None = None,
) -> Dict[str, Any]:
    """Persist kill-switch activation and return state payload."""

    state_dir = state_dir or Path("artifacts/reports/mahnwesen") / tenant_id / "operate"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "operate_state.json"

    if state_file.exists():
        with state_file.open("r", encoding="utf-8") as fp:
            current = json.load(fp)
    else:
        current = {}

    if current.get("kill_switch") is True:
        # Already active; ensure idempotency by keeping existing reason/trace where set.
        if not current.get("reason"):
            current["reason"] = reason
        if not current.get("trace_id"):
            current["trace_id"] = trace_id
        payload = current
    else:
        payload = {
            "kill_switch": True,
            "reason": reason,
            "trace_id": trace_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    with state_file.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, ensure_ascii=False)

    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Activate Mahnwesen operate kill switch")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    parser.add_argument("--reason", required=True, help="Backout reason")
    parser.add_argument("--trace-id", required=True, help="Trace identifier")
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="Override state directory (defaults to artifacts/reports/mahnwesen/<tenant>/operate)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        payload = apply_kill_switch(
            tenant_id=args.tenant,
            reason=args.reason,
            trace_id=args.trace_id,
            state_dir=args.state_dir,
        )
        print(json.dumps(payload, ensure_ascii=False))
        print(
            f"KILL SWITCH ON for {args.tenant} – reason={payload['reason']} trace_id={payload['trace_id']}"
        )
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

