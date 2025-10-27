from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.core.config import settings

Reason = Literal["missing", "malformed", "unknown", "ok"]


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass
class TenantValidationResult:
    ok: bool
    reason: Reason


class TenantAllowlistLoader:
    """Load and cache tenant allowlist from ENV or a JSON/YAML file.

    - ENV: TENANT_ALLOWLIST (CSV of UUIDs)
    - FILE: TENANT_ALLOWLIST_PATH (JSON list or YAML with key 'tenants')
    - Optional hot-reload controlled by TENANT_ALLOWLIST_REFRESH_SEC (0=disabled)
    """

    def __init__(self) -> None:
        self._source: str = "env"
        self._path: Path | None = None
        self._allow: set[str] = set()
        self._mtime: float | None = None
        self._last_load: float = 0.0
        self._refresh_sec: int = int(getattr(settings, "TENANT_ALLOWLIST_REFRESH_SEC", 0) or 0)
        self._init_from_env_or_file()

    def _init_from_env_or_file(self) -> None:
        path = (getattr(settings, "TENANT_ALLOWLIST_PATH", "") or "").strip()
        if path:
            self._source = "file"
            self._path = Path(path)
        else:
            self._source = "env"
            self._path = None
        self._load()

    def _read_file_allowlist(self) -> set[str]:
        if not self._path or not self._path.exists():
            return set()
        text = self._path.read_text(encoding="utf-8")
        # Try JSON first
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return {str(x).strip() for x in data if isinstance(x, str)}
            if isinstance(data, dict) and "tenants" in data and isinstance(data["tenants"], list):
                return {str(x).strip() for x in data["tenants"] if isinstance(x, str)}
        except Exception:
            pass
        # Naive YAML: match UUID-like tokens
        return set(UUID_RE.findall(text))

    def _read_env_allowlist(self) -> set[str]:
        raw = (getattr(settings, "TENANT_ALLOWLIST", "") or "").strip()
        if not raw:
            return set()
        return {t.strip() for t in raw.split(",") if t.strip()}

    def _load(self) -> None:
        if self._source == "file":
            self._allow = {t.lower() for t in self._read_file_allowlist() if UUID_RE.match(t)}
            self._mtime = self._path.stat().st_mtime if self._path and self._path.exists() else None
        else:
            self._allow = {t.lower() for t in self._read_env_allowlist() if UUID_RE.match(t)}
            self._mtime = None
        self._last_load = time.time()

    def maybe_reload(self) -> None:
        if self._refresh_sec <= 0:
            return
        now = time.time()
        if now - self._last_load < self._refresh_sec:
            return
        if self._source == "file" and self._path and self._path.exists():
            mtime = self._path.stat().st_mtime
            if not self._mtime or mtime > self._mtime:
                self._load()
        elif self._source == "env":
            # Always reload env on interval
            self._load()

    def validate(self, uuid_str: str | None) -> TenantValidationResult:
        self.maybe_reload()
        if not uuid_str:
            return TenantValidationResult(ok=False, reason="missing")
        candidate = uuid_str.strip().lower()
        if not UUID_RE.match(candidate):
            return TenantValidationResult(ok=False, reason="malformed")
        # In development mode, allow any valid UUID if allowlist is empty
        if not self._allow and getattr(settings, "app_env", "production") == "development":
            return TenantValidationResult(ok=True, reason="ok")
        if candidate not in self._allow:
            return TenantValidationResult(ok=False, reason="unknown")
        return TenantValidationResult(ok=True, reason="ok")

    def info(self) -> tuple[str, str, int, set[str]]:
        """Return (source, version, count, allowlist). Version is 'env' or mtime string."""
        self.maybe_reload()
        if self._source == "file":
            version = str(int(self._mtime or 0))
        else:
            version = "env"
        return self._source, version, len(self._allow), set(self._allow)


# Global loader instance
loader = TenantAllowlistLoader()


def validate_tenant(uuid_str: str | None) -> TenantValidationResult:
    return loader.validate(uuid_str)
