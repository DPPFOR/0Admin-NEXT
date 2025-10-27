"""JSON logging utilities for the MCP server."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter adding an ISO timestamp and merging the event payload."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        event: dict[str, object] = getattr(record, "event", {})
        payload: dict[str, object] = {
            "ts": datetime.now(tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if event:
            payload.update(event)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> logging.Logger:
    """Configure root logger for the MCP server and return it."""
    logger = logging.getLogger("backend.mcp_server")
    if logger.handlers:
        logger.setLevel(level)
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


@contextmanager
def tool_log_context(
    *,
    tool: str,
    tenant_id: str,
    trace_id: str,
    payload: dict[str, object] | None = None,
) -> Iterator[None]:
    """Capture execution timing and write a single structured log entry."""

    logger = logging.getLogger("backend.mcp_server")
    started = time.perf_counter()
    status = "ok"
    error_message: str | None = None
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - re-raise after logging
        status = "error"
        error_message = str(exc)
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        event = {
            "tool": tool,
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "duration_ms": duration_ms,
            "status": status,
        }
        if payload:
            event["payload"] = payload
        if error_message:
            event["error"] = error_message
        logger.info("tool.execution", extra={"event": event})
