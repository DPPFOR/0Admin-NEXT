"""Adapter for ops.outbox_status (deterministic, no egress)."""

from __future__ import annotations

from typing import Any


class OutboxStatusAdapter:
    @staticmethod
    def describe() -> str:
        return "Outbox status adapter returning fixed counts."

    @staticmethod
    def plan(tenant_id: str | None = None, window: str | None = None) -> dict[str, Any]:
        # Deterministic counts; independent of inputs
        return {"counts": {"pending": 1, "processing": 0, "sent": 0, "failed": 0}}
