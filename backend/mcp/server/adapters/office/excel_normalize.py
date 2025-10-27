from __future__ import annotations

from typing import Any


def _valid_path(p: str) -> bool:
    return p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


class ExcelNormalizeAdapter:
    @staticmethod
    def describe() -> str:
        return "Normalize excel to CSV/schema report (stub)"

    @staticmethod
    def plan(path: str, tenant_id: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        if not isinstance(path, str) or not _valid_path(path):
            raise ValueError("VALIDATION: invalid path")
        report = {"sheets": [{"name": "sheet1", "columns": ["col_a", "col_b"]}]}
        return {"report": report, "ts": "2025-01-01T00:00:00Z"}
