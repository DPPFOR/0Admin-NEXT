"""Evaluate Mahnwesen canary readiness for scaling from 10 % to 25 %."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple


@dataclass
class CanaryThresholds:
    success_rate: float = 0.97
    error_rate: float = 0.01
    dlq_depth: int = 0
    hard_bounce_rate: float = 0.05


def evaluate_canary(
    *,
    success_rate: float,
    error_rate: float,
    dlq_depth: int,
    hard_bounce_rate: float,
    thresholds: CanaryThresholds | None = None,
) -> Tuple[str, List[str]]:
    """Return decision and reasoning for canary escalation."""

    thresholds = thresholds or CanaryThresholds()
    reasons: List[str] = []

    if success_rate < thresholds.success_rate:
        reasons.append(
            f"Success rate {success_rate:.3%} below target {thresholds.success_rate:.0%}"
        )
    if error_rate > thresholds.error_rate:
        reasons.append(
            f"Error rate {error_rate:.3%} exceeds limit {thresholds.error_rate:.0%}"
        )
    if dlq_depth > thresholds.dlq_depth:
        reasons.append(f"DLQ depth {dlq_depth} > {thresholds.dlq_depth}")
    if hard_bounce_rate > thresholds.hard_bounce_rate:
        reasons.append(
            f"Hard bounce {hard_bounce_rate:.3%} exceeds limit {thresholds.hard_bounce_rate:.0%}"
        )

    decision = "GO_25" if not reasons else "HOLD"
    if decision == "GO_25":
        reasons.append("Metrics within thresholds for scaling to 25 %")

    return decision, reasons


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Mahnwesen canary decision")
    parser.add_argument("--tenant", required=True, help="Tenant UUID under consideration")
    parser.add_argument(
        "--success-rate",
        type=float,
        required=True,
        help="Success rate (0-1)",
    )
    parser.add_argument(
        "--error-rate",
        type=float,
        required=True,
        help="Error rate (0-1)",
    )
    parser.add_argument(
        "--dlq-depth",
        type=int,
        required=True,
        help="Current DLQ depth",
    )
    parser.add_argument(
        "--hard-bounce-rate",
        type=float,
        required=True,
        help="Hard bounce rate (0-1)",
    )
    parser.add_argument("--trace-id", help="Correlation trace id")
    parser.add_argument("--output-json", action="store_true", help="Emit JSON only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        decision, reasons = evaluate_canary(
            success_rate=args.success_rate,
            error_rate=args.error_rate,
            dlq_depth=args.dlq_depth,
            hard_bounce_rate=args.hard_bounce_rate,
        )

        payload: Dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "tenant_id": args.tenant,
            "trace_id": args.trace_id
            or f"canary-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "decision": decision,
            "metrics": {
                "success_rate": args.success_rate,
                "error_rate": args.error_rate,
                "dlq_depth": args.dlq_depth,
                "hard_bounce_rate": args.hard_bounce_rate,
            },
            "thresholds": CanaryThresholds().__dict__,
            "reasons": reasons,
        }

        json_payload = json.dumps(payload, ensure_ascii=False)
        print(json_payload)
        if not args.output_json:
            if decision == "GO_25":
                print("GO 25 % – " + reasons[-1])
            else:
                print("HOLD – " + "; ".join(reasons))
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

