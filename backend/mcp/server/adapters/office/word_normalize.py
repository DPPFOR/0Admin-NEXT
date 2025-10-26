from __future__ import annotations

from typing import Any, Dict


def _valid_path(p: str) -> bool:
    return p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


class WordNormalizeAdapter:
    @staticmethod
    def describe() -> str:
        return "Normalize .docx to MD/plain report (stub)"

    @staticmethod
    def plan(path: str, tenant_id: str | None = None, dry_run: bool = True) -> Dict[str, Any]:
        if not isinstance(path, str) or not _valid_path(path):
            raise ValueError("VALIDATION: invalid path")
        report = {"artifacts": [path.replace(".docx", ".md")]}
        return {"report": report, "ts": "2025-01-01T00:00:00Z"}

