"""Adapters related to ops.health_check and ops.dlq_list.

Deterministic, no egress. Provide describe() and plan() methods.
"""

from __future__ import annotations

from typing import Any


class HealthCheckAdapter:
    @staticmethod
    def describe() -> str:
        return "Simple local health check adapter (deterministic)."

    @staticmethod
    def plan(version: str) -> dict[str, Any]:
        # RFC3339 fixed timestamp string (deterministic)
        return {"status": "ok", "version": version, "ts": "2025-01-01T00:00:00Z"}


class DLQListAdapter:
    @staticmethod
    def describe() -> str:
        return "DLQ list adapter (no network), opaque cursors."

    @staticmethod
    def plan(
        tenant_id: str | None = None, limit: int = 50, cursor: str | None = None
    ) -> dict[str, Any]:
        # Always return empty items deterministically; do not touch network/DB
        result: dict[str, Any] = {"items": []}
        # Provide a deterministic next_cursor only when limit == 50 (arbitrary but deterministic rule)
        if limit == 50 and cursor is None:
            result["next_cursor"] = "QUJDREVGR0g="  # base64 of 'ABCDEFGH'
        return result
