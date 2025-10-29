"""Audit-Notices für Factur-X Pipeline (Approve/Reject)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .summary import mask_pii


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _write_notice(
    invoice_dir: Path,
    invoice_no: str,
    status: str,
    now: datetime,
    *,
    actor: str = "system",
    comment: Optional[str] = None,
) -> Path:
    audit_dir = invoice_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    now_utc = _ensure_utc(now)
    timestamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    filename = f"NOTICE-{invoice_no}_{status}_{timestamp}.json"
    payload = {
        "invoice_no": invoice_no,
        "status": status,
        "timestamp_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "actor": actor,
    }
    if comment:
        payload["comment"] = mask_pii(comment)

    path = audit_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def approve(
    invoice_dir: Path,
    invoice_no: str,
    now: datetime,
    *,
    actor: str = "system",
    comment: Optional[str] = None,
) -> Path:
    return _write_notice(invoice_dir, invoice_no, "approved", now, actor=actor, comment=comment)


def reject(
    invoice_dir: Path,
    invoice_no: str,
    now: datetime,
    *,
    reason: str,
    actor: str = "system",
) -> Path:
    return _write_notice(invoice_dir, invoice_no, "rejected", now, actor=actor, comment=reason)

