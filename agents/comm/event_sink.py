"""WORM-light event persistence with idempotency."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from agents.comm.events import CommEvent


class IdempotencyCache:
    """Thread-safe idempotency cache per day."""

    def __init__(self, date_str: str, cache_dir: Path):
        """Initialize cache for a specific date.

        Args:
            date_str: Date string (YYYYMMDD)
            cache_dir: Cache directory
        """
        self.date_str = date_str
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / f".idempotency-{date_str}.lock"
        self._seen: set[str] = set()
        self._lock = Lock()
        self._load_cache()

    def _load_cache(self) -> None:
        """Load existing cache from lockfile."""
        if self.cache_file.exists():
            try:
                content = self.cache_file.read_text(encoding="utf-8")
                seen_ids = [line.strip() for line in content.splitlines() if line.strip()]
                self._seen.update(seen_ids)
            except Exception:
                pass

    def _save_cache(self) -> None:
        """Save cache to lockfile."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text("\n".join(sorted(self._seen)), encoding="utf-8")
        except Exception:
            pass

    def is_seen(self, idempotency_key: str) -> bool:
        """Check if key was already seen.

        Args:
            idempotency_key: Idempotency key (provider|event_id)

        Returns:
            True if key was seen
        """
        with self._lock:
            return idempotency_key in self._seen

    def mark_seen(self, idempotency_key: str) -> None:
        """Mark key as seen.

        Args:
            idempotency_key: Idempotency key
        """
        with self._lock:
            self._seen.add(idempotency_key)
            self._save_cache()


class EventSink:
    """WORM-light event persistence with idempotency."""

    def __init__(self, base_dir: Path | None = None):
        """Initialize event sink.

        Args:
            base_dir: Base directory for artifacts (default: artifacts/events)
        """
        if base_dir is None:
            base_dir = Path("artifacts") / "events"
        self.base_dir = Path(base_dir)
        self._caches: dict[str, IdempotencyCache] = {}
        self._cache_lock = Lock()

    def _get_cache(self, tenant_id: str, date_str: str) -> IdempotencyCache:
        """Get or create idempotency cache for tenant/date.

        Args:
            tenant_id: Tenant UUID
            date_str: Date string (YYYYMMDD)

        Returns:
            Idempotency cache
        """
        cache_key = f"{tenant_id}:{date_str}"
        if cache_key not in self._caches:
            tenant_dir = self.base_dir / tenant_id / date_str
            with self._cache_lock:
                if cache_key not in self._caches:
                    self._caches[cache_key] = IdempotencyCache(date_str, tenant_dir)
        return self._caches[cache_key]

    def _build_idempotency_key(self, event: CommEvent) -> str:
        """Build idempotency key from event.

        Args:
            event: Communication event

        Returns:
            Idempotency key (provider|event_id)
        """
        provider = event.provider
        event_id = event.provider_event_id or event.message_id or str(uuid4())
        return f"{provider}|{event_id}"

    def persist(self, event: CommEvent) -> tuple[bool, Path | None]:
        """Persist event with idempotency check.

        Args:
            event: Communication event

        Returns:
            Tuple (was_persisted, file_path)
        """
        # Build date string
        date_str = event.ts.strftime("%Y%m%d")

        # Get cache
        cache = self._get_cache(event.tenant_id, date_str)

        # Build idempotency key
        idempotency_key = self._build_idempotency_key(event)

        # Check idempotency
        if cache.is_seen(idempotency_key):
            return False, None

        # Mark as seen
        cache.mark_seen(idempotency_key)

        # Build paths
        tenant_dir = self.base_dir / event.tenant_id / date_str
        tenant_dir.mkdir(parents=True, exist_ok=True)

        # Generate event ID
        event_id = str(uuid4())
        event_file = tenant_dir / f"event-{event_id}.json"
        ndjson_file = tenant_dir / "events.ndjson"

        # Prepare event dict (JSON-serializable)
        event_dict = event.model_dump(mode="json")
        event_dict["event_id"] = event_id
        event_dict["idempotency_key"] = idempotency_key

        # Write individual event file
        event_file.write_text(json.dumps(event_dict, indent=2, default=str), encoding="utf-8")

        # Append to NDJSON stream
        ndjson_line = json.dumps(event_dict, default=str)
        with ndjson_file.open("a", encoding="utf-8") as f:
            f.write(ndjson_line + "\n")

        return True, event_file

