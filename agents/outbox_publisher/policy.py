from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from backend.core.config import settings


def backoff_seconds(attempt: int) -> int:
    steps = [int(x.strip()) for x in settings.PUBLISH_BACKOFF_STEPS.split(",") if x.strip()]
    idx = min(max(attempt - 1, 0), len(steps) - 1) if steps else 0
    return steps[idx] if steps else 30


def next_attempt_time(now: datetime, attempt: int) -> datetime:
    return now + timedelta(seconds=backoff_seconds(attempt))

