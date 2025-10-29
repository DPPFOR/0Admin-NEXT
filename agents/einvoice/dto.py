"""Datentransferobjekte für EN16931 (A1 Foundations).

Die Datenstrukturen sind vollständig in-memory, deterministisch und nutzen
`Decimal` mit `ROUND_HALF_UP`, um Beträge auf zwei Nachkommastellen zu
quantisieren. Alle Methoden sind so gestaltet, dass identische Eingaben identische
Ergebnisse liefern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Dict, Iterable, List, Optional


DecimalLike = Decimal | str | int | float


def _to_decimal(value: DecimalLike) -> Decimal:
    """Konvertiere Eingaben deterministisch in ``Decimal``.

    Floats werden zunächst in Strings umgewandelt, um binäre Rundungsfehler zu
    vermeiden. Dadurch ergibt sich ein reproduzierbares Ergebnis unabhängig vom
    Host-System.
    """

    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        return Decimal(str(value))
    if isinstance(value, float):
        return Decimal(str(value))
    raise TypeError(f"Unsupported decimal input: {type(value)!r}")


def quantize_money(amount: DecimalLike) -> Decimal:
    """Rundet Beträge auf zwei Nachkommastellen (ROUND_HALF_UP)."""

    return _to_decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Address:
    street: str
    postal_code: str
    city: str
    country_code: str


@dataclass(frozen=True, slots=True)
class Party:
    name: str
    address: Address
    tax_id: Optional[str] = None
    vat_id: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    leitweg_id: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Tax:
    rate: Decimal
    category_code: str = "S"  # Standard rate per EN16931 (S = Standard rate)
    exemption_reason: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", quantize_money(self.rate))


@dataclass(slots=True)
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax: Tax
    line_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _to_decimal(self.quantity))
        object.__setattr__(self, "unit_price", _to_decimal(self.unit_price))

    def net_amount(self) -> Decimal:
        return quantize_money(self.quantity * self.unit_price)

    def tax_amount(self) -> Decimal:
        basis = self.net_amount()
        rate_factor = self.tax.rate / Decimal("100")
        return quantize_money(basis * rate_factor)

    def gross_amount(self) -> Decimal:
        return quantize_money(self.net_amount() + self.tax_amount())


@dataclass(slots=True)
class Totals:
    net_by_rate: Dict[Decimal, Decimal]
    tax_by_rate: Dict[Decimal, Decimal]
    total_net: Decimal
    total_tax: Decimal
    total_gross: Decimal

    def net_for_rate(self, rate: DecimalLike) -> Decimal:
        rate_decimal = quantize_money(rate)
        return self.net_by_rate.get(rate_decimal, Decimal("0.00"))

    def tax_for_rate(self, rate: DecimalLike) -> Decimal:
        rate_decimal = quantize_money(rate)
        return self.tax_by_rate.get(rate_decimal, Decimal("0.00"))


@dataclass(slots=True)
class Invoice:
    invoice_id: str
    tenant_id: str
    currency: str
    seller: Party
    buyer: Party
    line_items: List[LineItem]
    issue_date: date
    due_date: date
    payment_terms: str
    format_hint: str = "EN16931-A1"
    now_provider: Callable[[], datetime] = field(default=_default_clock, repr=False)
    invoice_no: Optional[str] = None

    _cached_totals: Optional[Totals] = field(default=None, init=False, repr=False)

    def compute_totals(self, *, force: bool = False) -> Totals:
        if self._cached_totals is not None and not force:
            return self._cached_totals

        if not self.line_items:
            raise ValueError("Invoice requires at least one line item")

        net_by_rate: Dict[Decimal, Decimal] = {}
        tax_by_rate: Dict[Decimal, Decimal] = {}

        for item in self.line_items:
            rate = item.tax.rate
            basis = item.net_amount()
            tax_amount = item.tax_amount()

            net_by_rate[rate] = quantize_money(net_by_rate.get(rate, Decimal("0.00")) + basis)
            tax_by_rate[rate] = quantize_money(tax_by_rate.get(rate, Decimal("0.00")) + tax_amount)

        total_net = quantize_money(sum(net_by_rate.values(), Decimal("0.00")))
        total_tax = quantize_money(sum(tax_by_rate.values(), Decimal("0.00")))
        total_gross = quantize_money(total_net + total_tax)

        totals = Totals(
            net_by_rate=dict(sorted(net_by_rate.items(), key=lambda kv: kv[0])),
            tax_by_rate=dict(sorted(tax_by_rate.items(), key=lambda kv: kv[0])),
            total_net=total_net,
            total_tax=total_tax,
            total_gross=total_gross,
        )
        self._cached_totals = totals
        return totals

    def validate(self) -> None:
        if not self.currency or len(self.currency) != 3:
            raise ValueError("Currency must be a 3-letter ISO code")
        if self.issue_date > self.due_date:
            raise ValueError("Due date must not be before issue date")
        self.compute_totals()

    def idempotency_key(self, invoice_no: str, format_name: str) -> str:
        return f"{self.tenant_id}|{invoice_no}|{format_name}"

    def touch(self) -> datetime:
        """Hilfsfunktion für Tests: gibt den deterministischen Zeitstempel zurück."""

        return self.now_provider()


def build_invoice(
    *,
    invoice_id: str,
    tenant_id: str,
    seller: Party,
    buyer: Party,
    line_items: Iterable[LineItem],
    issue_date: date,
    due_date: date,
    payment_terms: str,
    currency: str = "EUR",
    now_provider: Callable[[], datetime] | None = None,
) -> Invoice:
    invoice = Invoice(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        currency=currency,
        seller=seller,
        buyer=buyer,
        line_items=list(line_items),
        issue_date=issue_date,
        due_date=due_date,
        payment_terms=payment_terms,
        now_provider=now_provider or _default_clock,
    )
    invoice.validate()
    return invoice

