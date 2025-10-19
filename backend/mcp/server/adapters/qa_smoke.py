"""Adapter for qa.run_smoke (deterministic, no egress)."""

from __future__ import annotations

from typing import Any, Dict, List


_ALLOWED = {"upload", "programmatic", "worker", "mail", "read_ops", "publisher"}


class QASmokeAdapter:
    @staticmethod
    def describe() -> str:
        return "QA smoke adapter with fixed suites and summary."

    @staticmethod
    def plan(selection: str, dry_run: bool = True) -> Dict[str, Any]:
        if selection not in _ALLOWED:
            # We don't throw; in real systems this would be VALIDATION. Here we encode a minimal signal.
            raise ValueError("VALIDATION: invalid selection")
        suites: List[Dict[str, Any]] = [
            {"name": selection, "cases": [{"name": "noop", "status": "ok"}]}
        ]
        summary = {"total": 1, "passed": 1, "failed": 0}
        return {"summary": summary, "suites": suites}

