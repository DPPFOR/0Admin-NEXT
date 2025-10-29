"""WORM-Light Archivierung und Manifest-Erzeugung für Factur-X-Belege."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Tuple


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hash_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def write_package(
    base_dir: Path,
    tenant_id: str,
    invoice_no: str,
    files: Dict[str, bytes],
    *,
    now: datetime,
    previous_hash: str | None,
    generator_version: str,
) -> Tuple[Path, str]:
    """Schreibt alle Artefakte und erzeugt ein Manifest mit Hash-Kette."""

    tenant_dir = (
        base_dir / "artifacts" / "reports" / "einvoice" / tenant_id / invoice_no
    )
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "audit").mkdir(parents=True, exist_ok=True)

    for name, content in sorted(files.items()):
        (tenant_dir / name).write_bytes(content)

    created_at = _ensure_utc(now).isoformat().replace("+00:00", "Z")
    file_hashes = {
        name: _hash_bytes(content) for name, content in sorted(files.items())
    }

    manifest = {
        "schema_version": "1.0",
        "generator_version": generator_version,
        "tenant_id": tenant_id,
        "invoice_no": invoice_no,
        "created_at_utc": created_at,
        "previous_hash": previous_hash,
        "files": file_hashes,
    }

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    (tenant_dir / "manifest.json").write_bytes(manifest_bytes)
    manifest_hash = _hash_bytes(manifest_bytes)
    return tenant_dir, manifest_hash

