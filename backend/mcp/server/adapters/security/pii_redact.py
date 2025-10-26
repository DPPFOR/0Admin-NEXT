from __future__ import annotations

from typing import Any, Dict, List


def _valid_path(p: str) -> bool:
    return p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


class SecurityPIIRedactAdapter:
    @staticmethod
    def describe() -> str:
        return "PII detection/masking plan (stub)"

    @staticmethod
    def plan(paths: List[str], tenant_id: str | None = None, dry_run: bool = True) -> Dict[str, Any]:
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and _valid_path(p) for p in paths):
            raise ValueError("VALIDATION: invalid paths")
        plan = {"steps": [{"op": "redact", "targets": paths}]}
        return {"plan": plan, "ts": "2025-01-01T00:00:00Z"}

