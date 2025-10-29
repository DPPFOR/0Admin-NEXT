"""Deterministische Beispielrechnungen für Factur-X Tests & CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Iterable, List

from .dto import Address, Invoice, LineItem, Party, Tax, build_invoice
from .stammdaten import TenantProfile


@dataclass(frozen=True)
class SampleScenario:
    code: str
    description: str
    line_specs: tuple[tuple[str, str, str, str], ...]


SELLER_PARTY = Party(
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

BUYER_PARTY = Party(
    name="Customer GmbH",
    address=Address(
        street="Customer Way 5",
        postal_code="20095",
        city="Hamburg",
        country_code="DE",
    ),
)


def _make_line(spec: tuple[str, str, str, str]) -> LineItem:
    description, quantity, unit_price, rate = spec
    return LineItem(
        description=description,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        tax=Tax(rate=Decimal(rate)),
    )


SCENARIOS: List[SampleScenario] = [
    SampleScenario("01", "single_19", (("Consulting", "1", "100.00", "19"),)),
    SampleScenario(
        "02",
        "dual_19",
        (
            ("Service A", "1", "80.00", "19"),
            ("Service B", "3", "20.00", "19"),
        ),
    ),
    SampleScenario(
        "03",
        "mixed_7_19",
        (
            ("Consulting", "1", "100.00", "19"),
            ("Books", "2", "30.00", "7"),
        ),
    ),
    SampleScenario("04", "zero_rate", (("Export", "5", "10.00", "0"),)),
    SampleScenario(
        "05",
        "mixed_all",
        (
            ("Consulting", "1", "100.00", "19"),
            ("Catering", "1", "50.00", "7"),
            ("Export", "1", "200.00", "0"),
        ),
    ),
    SampleScenario(
        "06",
        "fractional_quantities",
        (
            ("Half-day consulting", "0.5", "199.99", "19"),
            ("Workshop", "1.25", "80.40", "7"),
        ),
    ),
    SampleScenario(
        "07",
        "high_quantity_mixed",
        (
            ("Item 19", "10", "15.00", "19"),
            ("Item 7", "5", "12.00", "7"),
            ("Item 0", "8", "5.00", "0"),
        ),
    ),
    SampleScenario(
        "08",
        "rounding_edge",
        (
            ("Edge A", "3", "33.333", "19"),
            ("Edge B", "4", "14.375", "7"),
        ),
    ),
    SampleScenario(
        "09",
        "large_values",
        (
            ("Big 19", "1", "1234.56", "19"),
            ("Big 7", "2", "789.10", "7"),
            ("Big 0", "3", "250.00", "0"),
        ),
    ),
    SampleScenario(
        "10",
        "mixed_zero_reduced_standard",
        (
            ("Subscription", "2", "45.50", "19"),
            ("Warranty", "5", "20.00", "0"),
            ("Reduced", "3", "18.90", "7"),
        ),
    ),
]


def iter_sample_scenarios() -> Iterable[SampleScenario]:
    return list(SCENARIOS)


def build_sample_invoice(
    scenario: SampleScenario,
    *,
    invoice_id: str,
    tenant_id: str,
    issue_date: date,
    due_date: date,
    payment_terms: str,
    now_provider: Callable[[], datetime],
) -> Invoice:
    line_items = [_make_line(spec) for spec in scenario.line_specs]
    return build_invoice(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        seller=SELLER_PARTY,
        buyer=BUYER_PARTY,
        line_items=line_items,
        issue_date=issue_date,
        due_date=due_date,
        payment_terms=payment_terms,
        now_provider=now_provider,
    )


def build_sample_profile(tenant_id: str, payment_terms: str = "14 Tage") -> TenantProfile:
    return TenantProfile(
        tenant_id=tenant_id,
        seller=SELLER_PARTY,
        payment_terms=payment_terms,
    )

