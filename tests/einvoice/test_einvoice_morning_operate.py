"""Tests for E-Invoice Morning Operate — auto-generated via PDD."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from tools.operate.einvoice_morning import run_morning_for_tenant


def test_einvoice_morning_dry_run(tmp_path: Path) -> None:
    """Prüft dass Dry-Run Summary erzeugt wird."""
    tenant_id = "test-tenant-001"
    report_date = date(2025, 1, 1)

    result = run_morning_for_tenant(
        tenant_id,
        report_date,
        dry_run=True,
        count_limit=5,
        format_name="facturx",
        base_path=tmp_path,
    )

    assert result["tenant_id"] == tenant_id
    assert result["report_date"] == report_date.isoformat()
    assert result["generate_info"]["count"] == 5

    # Summary sollte existieren (auch im Dry-Run)
    summary_path = Path(result["summary_path"])
    assert summary_path.exists(), "Summary file missing"
    summary_content = summary_path.read_text(encoding="utf-8")
    assert "DRY-RUN" in summary_content
    assert tenant_id in summary_content


def test_einvoice_morning_kpi_plausibility(tmp_path: Path) -> None:
    """Prüft dass KPI-Werte plausibel sind."""
    tenant_id = "test-tenant-002"
    report_date = date(2025, 1, 2)

    result = run_morning_for_tenant(
        tenant_id,
        report_date,
        dry_run=False,
        count_limit=10,
        format_name="facturx",
        base_path=tmp_path,
    )

    kpi_report = result.get("kpi_report")
    if kpi_report:
        metrics = kpi_report.get("metrics", {})
        assert metrics.get("count_total", 0) >= 0
        assert metrics.get("count_ok", 0) >= 0
        assert metrics.get("schema_fail", 0) >= 0
        assert metrics.get("schematron_fail", 0) >= 0
        
        # Wenn Invoices generiert wurden, sollten KPIs vorhanden sein
        if result["generate_info"]["count"] > 0:
            assert metrics.get("count_total", 0) > 0


def test_einvoice_morning_no_pii(tmp_path: Path) -> None:
    """Prüft dass keine PII in Summary enthalten ist."""
    tenant_id = "test-tenant-003"
    report_date = date(2025, 1, 3)

    result = run_morning_for_tenant(
        tenant_id,
        report_date,
        dry_run=True,
        count_limit=3,
        format_name="facturx",
        base_path=tmp_path,
    )

    summary_path = Path(result["summary_path"])
    summary_content = summary_path.read_text(encoding="utf-8")

    # Prüfe auf häufige PII-Patterns
    assert "@" not in summary_content or "<EMAIL>" in summary_content, "Potential email in summary"
    assert "DE" not in summary_content or "VAT_ID" in summary_content or len(summary_content.split("DE")) < 3, "Potential VAT-ID in summary"


def test_einvoice_morning_deterministic_times(tmp_path: Path) -> None:
    """Prüft deterministische Zeiten (UTC)."""
    tenant_id = "test-tenant-004"
    report_date = date(2025, 1, 4)

    # Setze deterministische Umgebung
    os.environ["TZ"] = "UTC"
    os.environ["PYTHONHASHSEED"] = "0"

    result = run_morning_for_tenant(
        tenant_id,
        report_date,
        dry_run=True,
        count_limit=3,
        format_name="facturx",
        base_path=tmp_path,
    )

    summary_path = Path(result["summary_path"])
    summary_content = summary_path.read_text(encoding="utf-8")

    # Prüfe dass UTC-Timestamps verwendet werden
    assert "2025-01-04" in summary_content
    assert "+00:00" in summary_content or "Z" in summary_content[-20:] or "UTC" in summary_content

