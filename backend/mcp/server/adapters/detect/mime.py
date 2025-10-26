from __future__ import annotations

from typing import Any, Dict, List


def _valid_path(p: str) -> bool:
    return p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


class DetectMimeAdapter:
    @staticmethod
    def describe() -> str:
        return "Detect MIME/types from local paths (stub, deterministic)."

    @staticmethod
    def plan(paths: List[str], tenant_id: str | None = None, dry_run: bool = True) -> Dict[str, Any]:
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and _valid_path(p) for p in paths):
            raise ValueError("VALIDATION: invalid paths")
        report = {"items": [{"path": p, "mime": "application/octet-stream"} for p in paths]}
        return {"report": report, "ts": "2025-01-01T00:00:00Z"}

