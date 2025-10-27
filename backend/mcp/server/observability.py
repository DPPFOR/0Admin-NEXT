"""Observability shim.

Tries to import a logger factory from backend.core.observability; if that fails,
falls back to a no-op logger with the same surface.
"""

from __future__ import annotations

from typing import Any


class _NullLogger:
    def debug(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial
        pass

    def info(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial
        pass

    def exception(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial
        pass


def get_logger(name: str = "mcp"):
    try:  # strict try/except with no side effects on failure
        from backend.core import observability as core_obs  # type: ignore

        if hasattr(core_obs, "get_logger"):
            return core_obs.get_logger(name)
    except Exception:
        pass
    return _NullLogger()
