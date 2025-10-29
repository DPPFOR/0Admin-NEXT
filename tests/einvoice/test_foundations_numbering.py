"""Tests for agents.einvoice foundations — auto-generated via PDD."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List

import pytest

from agents.einvoice.dto import Address, LineItem, Party, Tax, build_invoice
from agents.einvoice.numbering import (
    NumberingService,
    ReservationStateError,
)
from agents.einvoice.stammdaten import TenantProfile, TenantProfileProvider


def _fixed_clock() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_line(description: str, quantity: str, unit_price: str, tax_rate: str) -> LineItem:
    return LineItem(
        description=description,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        tax=Tax(rate=Decimal(tax_rate)),
    )


SELLER = Party(
    name="Tenant Seller",
    address=Address(
        street="Sample Street 1",
        postal_code="10115",
        city="Berlin",
        country_code="DE",
    ),
    vat_id="DE123456789",
    iban="DE02120300000000202051",
)


BUYER = Party(
    name="Customer GmbH",
    address=Address(
        street="Customer Way 5",
        postal_code="20095",
        city="Hamburg",
        country_code="DE",
    ),
)


@dataclass
class InvoiceScenario:
    name: str
    lines: List[LineItem]
    expected_net: Dict[Decimal, Decimal]
    expected_tax: Dict[Decimal, Decimal]
    total_net: Decimal
    total_tax: Decimal
    total_gross: Decimal


SCENARIOS: List[InvoiceScenario] = [
    InvoiceScenario(
        name="single_19",
        lines=[make_line("Consulting", "1", "100.00", "19")],
        expected_net={Decimal("19.00"): Decimal("100.00")},
        expected_tax={Decimal("19.00"): Decimal("19.00")},
        total_net=Decimal("100.00"),
        total_tax=Decimal("19.00"),
        total_gross=Decimal("119.00"),
    ),
    InvoiceScenario(
        name="dual_19",
        lines=[
            make_line("Service A", "1", "80.00", "19"),
            make_line("Service B", "3", "20.00", "19"),
        ],
        expected_net={Decimal("19.00"): Decimal("140.00")},
        expected_tax={Decimal("19.00"): Decimal("26.60")},
        total_net=Decimal("140.00"),
        total_tax=Decimal("26.60"),
        total_gross=Decimal("166.60"),
    ),
    InvoiceScenario(
        name="mixed_7_19",
        lines=[
            make_line("Consulting", "1", "100.00", "19"),
            make_line("Books", "2", "30.00", "7"),
        ],
        expected_net={
            Decimal("7.00"): Decimal("60.00"),
            Decimal("19.00"): Decimal("100.00"),
        },
        expected_tax={
            Decimal("7.00"): Decimal("4.20"),
            Decimal("19.00"): Decimal("19.00"),
        },
        total_net=Decimal("160.00"),
        total_tax=Decimal("23.20"),
        total_gross=Decimal("183.20"),
    ),
    InvoiceScenario(
        name="zero_rate",
        lines=[make_line("Export", "5", "10.00", "0")],
        expected_net={Decimal("0.00"): Decimal("50.00")},
        expected_tax={Decimal("0.00"): Decimal("0.00")},
        total_net=Decimal("50.00"),
        total_tax=Decimal("0.00"),
        total_gross=Decimal("50.00"),
    ),
    InvoiceScenario(
        name="mixed_all",
        lines=[
            make_line("Consulting", "1", "100.00", "19"),
            make_line("Catering", "1", "50.00", "7"),
            make_line("Export", "1", "200.00", "0"),
        ],
        expected_net={
            Decimal("0.00"): Decimal("200.00"),
            Decimal("7.00"): Decimal("50.00"),
            Decimal("19.00"): Decimal("100.00"),
        },
        expected_tax={
            Decimal("0.00"): Decimal("0.00"),
            Decimal("7.00"): Decimal("3.50"),
            Decimal("19.00"): Decimal("19.00"),
        },
        total_net=Decimal("350.00"),
        total_tax=Decimal("22.50"),
        total_gross=Decimal("372.50"),
    ),
    InvoiceScenario(
        name="fractional_quantities",
        lines=[
            make_line("Half-day consulting", "0.5", "199.99", "19"),
            make_line("Workshop", "1.25", "80.40", "7"),
        ],
        expected_net={
            Decimal("7.00"): Decimal("100.50"),
            Decimal("19.00"): Decimal("100.00"),
        },
        expected_tax={
            Decimal("7.00"): Decimal("7.04"),
            Decimal("19.00"): Decimal("19.00"),
        },
        total_net=Decimal("200.50"),
        total_tax=Decimal("26.04"),
        total_gross=Decimal("226.54"),
    ),
    InvoiceScenario(
        name="high_quantity_mixed",
        lines=[
            make_line("Item 19", "10", "15.00", "19"),
            make_line("Item 7", "5", "12.00", "7"),
            make_line("Item 0", "8", "5.00", "0"),
        ],
        expected_net={
            Decimal("0.00"): Decimal("40.00"),
            Decimal("7.00"): Decimal("60.00"),
            Decimal("19.00"): Decimal("150.00"),
        },
        expected_tax={
            Decimal("0.00"): Decimal("0.00"),
            Decimal("7.00"): Decimal("4.20"),
            Decimal("19.00"): Decimal("28.50"),
        },
        total_net=Decimal("250.00"),
        total_tax=Decimal("32.70"),
        total_gross=Decimal("282.70"),
    ),
    InvoiceScenario(
        name="rounding_edge",
        lines=[
            make_line("Edge A", "3", "33.333", "19"),
            make_line("Edge B", "4", "14.375", "7"),
        ],
        expected_net={
            Decimal("7.00"): Decimal("57.50"),
            Decimal("19.00"): Decimal("100.00"),
        },
        expected_tax={
            Decimal("7.00"): Decimal("4.03"),
            Decimal("19.00"): Decimal("19.00"),
        },
        total_net=Decimal("157.50"),
        total_tax=Decimal("23.03"),
        total_gross=Decimal("180.53"),
    ),
    InvoiceScenario(
        name="large_values",
        lines=[
            make_line("Big 19", "1", "1234.56", "19"),
            make_line("Big 7", "2", "789.10", "7"),
            make_line("Big 0", "3", "250.00", "0"),
        ],
        expected_net={
            Decimal("0.00"): Decimal("750.00"),
            Decimal("7.00"): Decimal("1578.20"),
            Decimal("19.00"): Decimal("1234.56"),
        },
        expected_tax={
            Decimal("0.00"): Decimal("0.00"),
            Decimal("7.00"): Decimal("110.47"),
            Decimal("19.00"): Decimal("234.57"),
        },
        total_net=Decimal("3562.76"),
        total_tax=Decimal("345.04"),
        total_gross=Decimal("3907.80"),
    ),
    InvoiceScenario(
        name="mixed_zero_reduced_standard",
        lines=[
            make_line("Subscription", "2", "45.50", "19"),
            make_line("Warranty", "5", "20.00", "0"),
            make_line("Reduced", "3", "18.90", "7"),
        ],
        expected_net={
            Decimal("0.00"): Decimal("100.00"),
            Decimal("7.00"): Decimal("56.70"),
            Decimal("19.00"): Decimal("91.00"),
        },
        expected_tax={
            Decimal("0.00"): Decimal("0.00"),
            Decimal("7.00"): Decimal("3.97"),
            Decimal("19.00"): Decimal("17.29"),
        },
        total_net=Decimal("247.70"),
        total_tax=Decimal("21.26"),
        total_gross=Decimal("268.96"),
    ),
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_compute_totals_is_deterministic(scenario: InvoiceScenario) -> None:
    # Arrange
    invoice = build_invoice(
        invoice_id=f"INV-{scenario.name}",
        tenant_id="tenant-1",
        seller=SELLER,
        buyer=BUYER,
        line_items=scenario.lines,
        issue_date=date(2025, 1, 1),
        due_date=date(2025, 1, 15),
        payment_terms="14 Tage",
        now_provider=_fixed_clock,
    )

    # Act
    totals = invoice.compute_totals()

    # Assert
    assert totals.net_by_rate == scenario.expected_net
    assert totals.tax_by_rate == scenario.expected_tax
    assert totals.total_net == scenario.total_net
    assert totals.total_tax == scenario.total_tax
    assert totals.total_gross == scenario.total_gross


def test_tenant_profile_provider_returns_fallback() -> None:
    # Arrange
    provider = TenantProfileProvider(default_tenant_id="tenant-default")
    default_profile = TenantProfile(
        tenant_id="tenant-default",
        seller=SELLER,
        payment_terms="14 Tage",
    )
    provider.register(default_profile)

    # Act
    result = provider.get("unknown-tenant")

    # Assert
    assert result == default_profile


def test_tenant_profile_provider_raises_without_fallback() -> None:
    # Arrange
    provider = TenantProfileProvider()

    # Act & Assert
    with pytest.raises(KeyError):
        provider.get("missing")


def test_numbering_service_commits_without_gaps() -> None:
    # Arrange
    service = NumberingService(clock=_fixed_clock)

    res_a = service.reserve("tenant-1", date(2025, 1, 1), channel="MAIL")
    res_b = service.reserve("tenant-1", date(2025, 1, 2))
    res_c = service.reserve("tenant-1", date(2025, 1, 3))

    # Act
    invoice_no_a = service.commit(res_a)
    invoice_no_b = service.commit(res_b)
    service.abort(res_c)
    res_d = service.reserve("tenant-1", date(2025, 1, 4))
    invoice_no_d = service.commit(res_d)

    # Assert
    assert invoice_no_a == "INV-MAIL-2025-00001"
    assert invoice_no_b == "INV-2025-00002"
    assert invoice_no_d == "INV-2025-00003"
    assert [entry["action"] for entry in service.audit_log] == [
        "reserve",
        "reserve",
        "reserve",
        "commit",
        "commit",
        "abort",
        "reserve",
        "commit",
    ]


def test_numbering_service_commit_is_idempotent() -> None:
    # Arrange
    service = NumberingService(clock=_fixed_clock)
    reservation_id = service.reserve("tenant-1", date(2025, 6, 1))

    # Act
    first = service.commit(reservation_id)
    second = service.commit(reservation_id)

    # Assert
    assert first == "INV-2025-00001"
    assert second == first
    reservation_entry = next(
        entry for entry in service.audit_log if entry["action"] == "commit"
    )
    assert reservation_entry["idempotency_key"] == "tenant-1|INV-2025-00001|einvoice-default"


def test_numbering_service_abort_blocks_commit() -> None:
    # Arrange
    service = NumberingService(clock=_fixed_clock)
    reservation_id = service.reserve("tenant-1", date(2025, 4, 1))

    # Act
    service.abort(reservation_id)

    # Assert
    with pytest.raises(ReservationStateError):
        service.commit(reservation_id)
    abort_entries = [entry for entry in service.audit_log if entry["action"] == "abort"]
    assert abort_entries

