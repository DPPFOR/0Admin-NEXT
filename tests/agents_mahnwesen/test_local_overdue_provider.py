"""Tests for LocalOverdueProvider — auto-generated via PDD."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agents.mahnwesen.providers import LocalOverdueProvider


TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def provider() -> LocalOverdueProvider:
    sent_path = (
        Path("artifacts/reports/mahnwesen")
        / TENANT_ID
        / "outbox"
        / "sent.json"
    )
    if sent_path.exists():
        sent_path.unlink()
    return LocalOverdueProvider()


def test_provider_returns_expected_distribution(provider: LocalOverdueProvider) -> None:
    invoices = provider.load_overdue_invoices(TENANT_ID)

    assert len(invoices) >= 4

    stage_counts = {1: 0, 2: 0, 3: 0}
    for invoice in invoices:
        assert invoice.tenant_id == TENANT_ID
        assert invoice.metadata["source"].startswith("artifacts/inbox_local/samples/")
        stage_counts[invoice.dunning_stage] += 1

    assert stage_counts[1] >= 2
    assert stage_counts[2] >= 1
    assert stage_counts[3] >= 1


@pytest.mark.parametrize(
    "limit,expected",
    [
        (None, 4),
        (2, 2),
    ],
)
def test_provider_limit(provider: LocalOverdueProvider, limit: int | None, expected: int) -> None:
    invoices = provider.load_overdue_invoices(TENANT_ID, limit=limit)
    assert len(invoices) == expected


def test_provider_masks_email(provider: LocalOverdueProvider) -> None:
    invoice = provider.load_overdue_invoices(TENANT_ID, limit=1)[0]
    assert invoice.customer_email.endswith("@example.com")
    assert "***" in invoice.customer_email


def test_provider_uses_static_due_dates(provider: LocalOverdueProvider) -> None:
    invoice = provider.load_overdue_invoices(TENANT_ID, limit=1)[0]
    assert isinstance(invoice.due_date, datetime)
    assert invoice.due_date.tzinfo is UTC

