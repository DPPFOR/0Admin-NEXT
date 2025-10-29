"""Tests for manifest generation — auto-generated via PDD."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from agents.einvoice.archive import write_package


def _sha(content: bytes) -> str:
    return sha256(content).hexdigest()


def test_manifest_contains_hash_chain(tmp_path: Path) -> None:
    base_dir = tmp_path
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)

    files_first = {
        "invoice.xml": b"<FacturX/>",
        "invoice.pdf": b"%PDF-1.4",
        "validation.json": b"{\"schema_ok\": true}",
    }

    first_dir, first_hash = write_package(
        base_dir,
        "tenant-test",
        "INV-2025-00001",
        files_first,
        now=now,
        previous_hash=None,
        generator_version="test-gen",
    )

    manifest_first = json.loads((first_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_first["previous_hash"] is None
    assert manifest_first["files"]["invoice.xml"] == _sha(files_first["invoice.xml"])

    files_second = {
        "invoice.xml": b"<FacturX id='2'/>",
        "invoice.pdf": b"%PDF-1.4-second",
        "validation.json": b"{\"schema_ok\": true}",
    }

    second_dir, second_hash = write_package(
        base_dir,
        "tenant-test",
        "INV-2025-00002",
        files_second,
        now=now,
        previous_hash=first_hash,
        generator_version="test-gen",
    )

    manifest_second_path = second_dir / "manifest.json"
    manifest_second = json.loads(manifest_second_path.read_text(encoding="utf-8"))
    assert manifest_second["previous_hash"] == first_hash
    assert manifest_second["created_at_utc"].endswith("Z")

    # Idempotenz: erneuter Write mit identischen Daten ändert Manifest nicht
    manifest_bytes_before = manifest_second_path.read_bytes()
    _, repeat_hash = write_package(
        base_dir,
        "tenant-test",
        "INV-2025-00002",
        files_second,
        now=now,
        previous_hash=first_hash,
        generator_version="test-gen",
    )
    assert repeat_hash == second_hash
    assert manifest_second_path.read_bytes() == manifest_bytes_before


@pytest.mark.parametrize(
    "filename,content",
    [
        ("invoice.xml", b"<a/>")
    ],
)
def test_manifest_hash_matches_files(tmp_path: Path, filename: str, content: bytes) -> None:
    base_dir = tmp_path
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    files = {
        filename: content,
        "invoice.pdf": b"%PDF",
        "validation.json": b"{}",
    }

    invoice_dir, _ = write_package(
        base_dir,
        "tenant-x",
        "INV-2025-12345",
        files,
        now=now,
        previous_hash=None,
        generator_version="test-gen",
    )
    manifest = json.loads((invoice_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"][filename] == _sha(content)

