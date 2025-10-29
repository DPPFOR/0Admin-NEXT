"""Redaction probe to ensure logs mask sensitive data."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ARTIFACT_PATH = Path("artifacts/tests/redaction_probe.json")


SAMPLES = {
    "email": "john.doe@example.com",
    "iban": "DE89370400440532013000",
    "phone": "030-1234567",
}


PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+"), "***@***"),
    (re.compile(r"DE\d{20}"), "DE****************"),
    (re.compile(r"\b\d{2,3}[- ]?\d{3}[- ]?\d{4,5}\b"), "***-***-****"),
]


def mask_text(text: str) -> str:
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class MaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = mask_text(record.msg)
        return True


def run_probe() -> dict[str, Any]:
    logger = logging.getLogger("redaction_probe")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.addFilter(MaskingFilter())
    logger.handlers = [handler]

    masked_outputs: dict[str, str] = {}
    for label, value in SAMPLES.items():
        logger.info(value)
        masked_outputs[label] = mask_text(value)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "samples": {
            key: {"original": value, "masked": masked_outputs[key]}
            for key, value in SAMPLES.items()
        },
        "patterns": [pattern.pattern for pattern, _ in PATTERNS],
    }


def main() -> int:
    result = run_probe()
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(ARTIFACT_PATH)}, ensure_ascii=False))
    print("Redaction probe completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

