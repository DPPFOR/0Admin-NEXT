"""Emit simulated Operate alerts for Mahnwesen canary monitoring."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any, Dict


ALERT_THRESHOLDS: Dict[str, float] = {
    "error_rate": 0.02,
    "dlq_depth": 10.0,
    "retry_depth": 50.0,
    "hard_bounce_rate": 0.05,
}


def build_alert(
    *,
    tenant_id: str | None,
    metric: str,
    value: float,
    threshold: float | None = None,
    severity: str | None = None,
    trace_id: str | None = None,
    target: str = "simulate",
) -> Dict[str, Any]:
    """Create the alert payload without side effects."""

    metric = metric.strip().lower()
    tenant_id = tenant_id or os.getenv("TENANT_DEFAULT", "unknown-tenant")
    threshold = threshold if threshold is not None else ALERT_THRESHOLDS.get(metric, value)
    trace_id = trace_id or f"trace-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    triggered = value > threshold
    if severity is None:
        severity = "critical" if triggered else "info"

    message = (
        f"[{severity.upper()}] {metric}={value} exceeded threshold {threshold}"
        if triggered
        else f"[{severity.upper()}] {metric} at {value} within threshold {threshold}"
    )

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "severity": severity,
        "metric": metric,
        "threshold": threshold,
        "value": value,
        "target": target,
        "message": message,
    }
    return payload


def emit_alert(args: argparse.Namespace) -> None:
    payload = build_alert(
        tenant_id=args.tenant,
        metric=args.metric,
        value=args.value,
        threshold=args.threshold,
        severity=args.severity,
        trace_id=args.trace_id,
        target=args.target,
    )

    json_payload = json.dumps(payload, ensure_ascii=False)
    print(json_payload)
    print(payload["message"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a simulated Operate alert for Mahnwesen monitoring",
    )
    parser.add_argument("--tenant", required=True, help="Tenant ID for the alert")
    parser.add_argument("--metric", required=True, help="Metric name (e.g. error_rate)")
    parser.add_argument(
        "--value",
        type=float,
        required=True,
        help="Observed value for the metric",
    )
    parser.add_argument("--threshold", type=float, help="Threshold for the metric")
    parser.add_argument("--severity", help="Override severity (info|warning|critical)")
    parser.add_argument("--trace-id", help="Trace identifier for correlation")
    parser.add_argument(
        "--target",
        default="simulate",
        help="Target integration (simulate/Slack/Email)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        emit_alert(args)
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

