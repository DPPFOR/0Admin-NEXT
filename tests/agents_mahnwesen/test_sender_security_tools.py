"""Tests for sender DNS and security tooling — auto-generated via PDD."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.operate.sender_dns_check import build_expectations, build_report
from tools.operate.sender_policy_probe import build_probe
from tools.operate.redaction_probe import mask_text


def test_build_expectations_contains_records() -> None:
    expectations = build_expectations("example.com")
    names = {exp.name for exp in expectations}
    assert "brevo._domainkey.example.com" in names
    assert any("spf.brevo.com" in exp.expected_value for exp in expectations)


def test_build_report_structure(tmp_path: Path) -> None:
    report = build_report("tenant-test", "example.com")
    assert report["status"] == "EXPECTED"
    assert len(report["records"]) >= 4
    record_names = [rec["name"] for rec in report["records"]]
    assert "_dmarc.example.com" in record_names


def test_build_probe_env_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREVO_API_KEY", "***")
    monkeypatch.delenv("BREVO_SENDER_NAME", raising=False)
    probe = build_probe("tenant-id")
    assert probe["env_status"]["BREVO_API_KEY"] == "SET"
    assert probe["env_status"]["BREVO_SENDER_NAME"] == "UNSET"
    assert probe["bounce_policy"]["soft"]["max_attempts"] == 3


@pytest.mark.parametrize(
    "text,expected",
    [
        ("john.doe@example.com", "***@***"),
        ("DE89370400440532013000", "DE****************"),
        ("030-1234567", "***-***-****"),
    ],
)
def test_mask_text(text: str, expected: str) -> None:
    assert expected in mask_text(text)

