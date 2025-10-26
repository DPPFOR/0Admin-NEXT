"""Adapter for etl.inbox_extract (deterministic, no egress)."""

from __future__ import annotations

from typing import Any, Dict, List


class ETLInboxExtractAdapter:
    @staticmethod
    def describe() -> str:
        return "ETL inbox extract adapter returning a static plan."

    @staticmethod
    def plan(tenant_id: str, remote_url: str, dry_run: bool = True) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = [
            {"name": "validate_inputs"},
            {"name": "list_inbox"},
            {"name": "prepare_manifest"},
        ]
        return {"plan": {"steps": steps}}

