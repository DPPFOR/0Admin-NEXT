"""In-process metrics counters and histograms."""

import time
from collections import defaultdict
from typing import Any

from backend.core.config import settings

# Global metrics storage
_metrics = defaultdict(lambda: {"count": 0, "sum": 0.0, "values": [], "buckets": defaultdict(int)})


def init_metrics() -> None:
    """Initialize metrics if enabled."""
    if not settings.enable_metrics:
        return


def increment_counter(name: str, labels: dict[str, str] = None, value: float = 1.0) -> None:
    """Increment a counter metric."""
    if not settings.enable_metrics:
        return

    key = name
    if labels:
        key += "{" + ",".join(f"{k}={v}" for k, v in labels.items()) + "}"

    _metrics[key]["count"] += value


def record_histogram(name: str, value: float, labels: dict[str, str] = None) -> None:
    """Record a histogram measurement."""
    if not settings.enable_metrics:
        return

    key = name
    if labels:
        key += "{" + ",".join(f"{k}={v}" for k, v in labels.items()) + "}"

    metrics = _metrics[key]
    metrics["count"] += 1
    metrics["sum"] += value
    metrics["values"].append(value)

    # Simple buckets for basic histogram visualization
    if value < 0.1:
        metrics["buckets"]["<0.1"] += 1
    elif value < 1:
        metrics["buckets"]["0.1-1.0"] += 1
    elif value < 10:
        metrics["buckets"]["1.0-10.0"] += 1
    elif value < 100:
        metrics["buckets"]["10.0-100.0"] += 1
    elif value < 1000:
        metrics["buckets"]["100.0-1000.0"] += 1
    else:
        metrics["buckets"][">=1000.0"] += 1


def observe_duration(start_time: float, name: str, labels: dict[str, str] = None) -> None:
    """Observe a duration measurement."""
    duration_ms = (time.time() - start_time) * 1000
    record_histogram(name, duration_ms, labels)


def get_metrics() -> dict[str, Any]:
    """Get current metrics snapshot."""
    if not settings.enable_metrics:
        return {"note": "metrics disabled"}

    # Calculate basic statistics for histograms
    result = {}
    for key, data in _metrics.items():
        metric_result = {"count": data["count"], "sum": data["sum"]}

        if data["values"]:
            values = data["values"]
            metric_result.update(
                {
                    "min": min(values),
                    "max": max(values),
                    "avg": data["sum"] / len(values),
                    "buckets": dict(data["buckets"]),
                }
            )

        result[key] = metric_result

    return result


def reset_metrics() -> None:
    """Reset all metrics (useful for testing)."""
    global _metrics
    _metrics.clear()


# Specific metrics functions for inbox monitoring
def increment_inbox_received() -> None:
    """Increment counter for received inbox items."""
    increment_counter("inbox_received_total")


def increment_inbox_validated() -> None:
    """Increment counter for validated inbox items."""
    increment_counter("inbox_validated_total")


def increment_dedupe_hits() -> None:
    """Increment counter for deduplication hits."""
    increment_counter("dedupe_hits_total")


def measure_ingest_duration(duration_ms: float) -> None:
    """Record ingest duration in milliseconds."""
    record_histogram("ingest_duration_ms", duration_ms)


# Parsing worker metrics
def increment_parsed_total() -> None:
    increment_counter("parsed_total")


def increment_parse_failures() -> None:
    increment_counter("parse_failures_total")


def add_chunk_bytes(n: int) -> None:
    increment_counter("chunk_bytes_total", value=float(n))


def record_parse_duration(duration_ms: float) -> None:
    record_histogram("parse_duration_ms", duration_ms)


def record_fetch_duration(duration_ms: float) -> None:
    """Record remote fetch duration in milliseconds for programmatic ingest."""
    record_histogram("fetch_duration_ms", duration_ms)


# Mail ingest metrics
def increment_mail_messages() -> None:
    increment_counter("mail_messages_total")


def increment_mail_attachments() -> None:
    increment_counter("mail_attachments_total")


def increment_mail_failures() -> None:
    increment_counter("mail_ingest_failures_total")


def increment_mail_deferred() -> None:
    """Increment counter for deferred (throttled) mail attachments."""
    increment_counter("mail_deferred_total")


def record_mail_ingest_duration(duration_ms: float) -> None:
    record_histogram("mail_ingest_duration_ms", duration_ms)


# Read/Ops API metrics
def increment_inbox_read() -> None:
    increment_counter("inbox_read_total")


def increment_parsed_read() -> None:
    increment_counter("parsed_read_total")


def record_read_duration(duration_ms: float) -> None:
    record_histogram("read_duration_ms", duration_ms)


def record_ops_duration(duration_ms: float) -> None:
    record_histogram("ops_duration_ms", duration_ms)


def increment_ops_replay_attempts(n: float = 1.0) -> None:
    increment_counter("ops_replay_attempts_total", value=n)


def increment_ops_replay_committed(n: float = 1.0) -> None:
    increment_counter("ops_replay_committed_total", value=n)


# Outbox publisher metrics
def increment_publisher_attempts(n: float = 1.0) -> None:
    increment_counter("publisher_attempts_total", value=n)


def increment_publisher_sent(n: float = 1.0) -> None:
    increment_counter("publisher_sent_total", value=n)


def increment_publisher_failures(n: float = 1.0) -> None:
    increment_counter("publisher_failures_total", value=n)


def record_publisher_lag(ms: float) -> None:
    record_histogram("publisher_lag_ms", ms)


def record_publish_duration(ms: float) -> None:
    record_histogram("publish_duration_ms", ms)


# Tenant policy metrics
def increment_tenant_validation_failure(reason: str) -> None:
    increment_counter("tenant_validation_failures_total", labels={"reason": reason})


def increment_tenant_unknown_dropped() -> None:
    increment_counter("tenant_unknown_dropped_total")
