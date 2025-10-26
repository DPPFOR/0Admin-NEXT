from __future__ import annotations

from typing import Any, Dict


def _valid_path(p: str) -> bool:
    return p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


class OutlookFetchAdapter:
    @staticmethod
    def describe() -> str:
        return ".msg samples + attachments intake plan (stub)"

    @staticmethod
    def plan(path: str, tenant_id: str | None = None, dry_run: bool = True) -> Dict[str, Any]:
        if not isinstance(path, str) or not _valid_path(path):
            raise ValueError("VALIDATION: invalid path")
        plan = {"steps": [{"op": "parse_msg", "src": path}, {"op": "extract_attachments"}]}
        return {"plan": plan, "ts": "2025-01-01T00:00:00Z"}

