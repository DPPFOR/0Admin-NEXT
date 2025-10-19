from __future__ import annotations

from typing import Any, Dict


def _valid_path(p: str) -> bool:
    return p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


class ArchiveUnpackAdapter:
    @staticmethod
    def describe() -> str:
        return "Unpack archives locally into artifacts/inbox (stub)."

    @staticmethod
    def plan(path: str, tenant_id: str | None = None, dry_run: bool = True) -> Dict[str, Any]:
        if not isinstance(path, str) or not _valid_path(path):
            raise ValueError("VALIDATION: invalid path")
        plan = {"actions": [{"op": "unpack", "src": path, "dst": "artifacts/inbox/unpacked/"}]}
        return {"plan": plan, "ts": "2025-01-01T00:00:00Z"}

