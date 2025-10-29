"""Notification helpers for Operate tooling.

The functions provided here deliberately avoid hard-coding any
third-party SDKs. They expose simple hooks so operators can plug in
Slack webhooks or SMTP later without code changes.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NotificationPayload:
    """Structured notification payload used across channels."""

    title: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "message": self.message,
            "details": self.details,
        }


def emit_stdout(payload: NotificationPayload) -> None:
    """Print notification as JSON + plain text (fallback channel)."""

    data = payload.to_dict()
    print(json.dumps(data, ensure_ascii=False))
    print(payload.message)


def maybe_emit_slack(payload: NotificationPayload) -> bool:
    """Send payload to Slack webhook if configured.

    Returns True when a webhook was used, False otherwise.
    No external dependency is introduced here; the payload is posted via
    urllib if a webhook is present.
    """

    webhook = os.getenv("SLACK_WEBHOOK")
    if not webhook:
        return False

    try:
        import urllib.request

        body = json.dumps({"text": f"*{payload.title}*\n{payload.message}"}).encode()
        request = urllib.request.Request(
            webhook,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:  # type: ignore[no-untyped-call]
            response.read()
        return True
    except Exception as exc:  # pragma: no cover - network optional
        logger.warning("Slack notification failed", extra={"error": str(exc)})
        return False


def mask_sensitive(text: str) -> str:
    import re

    for pattern, replacement in MASK_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def write_markdown_summary(path: Path, heading: str, lines: list[str]) -> None:
    """Persist a short Markdown summary for operators."""

    path.parent.mkdir(parents=True, exist_ok=True)
    content = [f"# {heading}", ""] + lines
    path.write_text("\n".join(content) + "\n", encoding="utf-8")

