from __future__ import annotations

from pathlib import Path

from backend.mcp.server import policy
import hashlib


def test_policy_defaults_when_missing(tmp_path: Path):
    # No files -> defaults
    p = policy.load_policy(base_dir=str(tmp_path))
    assert p.dry_run_default is True
    assert p.allowed_tools == ["ops.health_check"]
    assert isinstance(p.quotas, dict) and p.quotas == {}


def test_policy_defaults_when_empty(tmp_path: Path):
    (tmp_path / "default-policy.yaml").write_text("\n", encoding="utf-8")
    p = policy.load_policy(base_dir=str(tmp_path))
    assert p.dry_run_default is True
    assert p.allowed_tools == ["ops.health_check"]


def test_quotas_parse_only(tmp_path: Path):
    (tmp_path / "default-policy.yaml").write_text("dry_run_default: false\nallowed_tools: [ops.health_check]", encoding="utf-8")
    (tmp_path / "quotas.example.yaml").write_text("tenants:\n  ACME:\n    rate: 10\n", encoding="utf-8")
    p = policy.load_policy(base_dir=str(tmp_path))
    assert p.dry_run_default is False
    assert p.allowed_tools == ["ops.health_check"]
    assert "tenants" in p.quotas and "ACME" in p.quotas["tenants"]


def test_policy_fingerprint_changes_with_missing_or_empty(tmp_path: Path):
    # Helper: compute fingerprint like validator does
    def compute_fp(base_dir: Path) -> str:
        dp = base_dir / "default-policy.yaml"
        if dp.exists() and dp.read_text(encoding="utf-8").strip():
            content = dp.read_text(encoding="utf-8").encode("utf-8")
        else:
            content = b"dry_run_default:true\nallowed_tools:[ops.health_check]\n"
        return hashlib.sha256(content).hexdigest()

    # Case 1: missing
    missing_fp = compute_fp(tmp_path)
    # Case 2: empty file
    (tmp_path / "default-policy.yaml").write_text("\n", encoding="utf-8")
    empty_fp = compute_fp(tmp_path)
    # Case 3: present content
    (tmp_path / "default-policy.yaml").write_text("dry_run_default: false\nallowed_tools: [ops.health_check]\n", encoding="utf-8")
    present_fp = compute_fp(tmp_path)

    assert missing_fp == empty_fp
    assert present_fp != missing_fp
