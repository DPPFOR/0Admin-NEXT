"""XRechnung (UBL) Generator – TEMP_XRECHNUNG_STUB."""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from typing import Iterable

from agents.einvoice.dto import Invoice, LineItem
from agents.einvoice.stammdaten import TenantProfile

XRECHNUNG_CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017"
XRECHNUNG_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
GENERATOR_VERSION = "xrechnung-ubl-stub-1"


def version() -> str:
    return GENERATOR_VERSION


def _format_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _format_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _aggregate_tax_items(line_items: Iterable[LineItem]) -> dict[Decimal, dict[str, Decimal]]:
    totals: dict[Decimal, dict[str, Decimal]] = {}
    for item in line_items:
        rate = item.tax.rate
        bucket = totals.setdefault(rate, {"net": Decimal("0.00"), "tax": Decimal("0.00")})
        bucket["net"] += item.net_amount()
        bucket["tax"] += item.tax_amount()
    return totals


def _render_invoice_line(index: int, item: LineItem, currency: str) -> str:
    quantity = _format_quantity(item.quantity)
    line_extension = _format_decimal(item.net_amount())
    unit_price = _format_decimal(item.unit_price)
    tax_rate = _format_decimal(item.tax.rate)
    return textwrap.dedent(
        f"""
        <cac:InvoiceLine>
          <cbc:ID>{index}</cbc:ID>
          <cbc:InvoicedQuantity>{quantity}</cbc:InvoicedQuantity>
          <cbc:LineExtensionAmount currencyID="{currency}">{line_extension}</cbc:LineExtensionAmount>
          <cac:Item>
            <cbc:Description>{escape(item.description)}</cbc:Description>
            <cac:ClassifiedTaxCategory>
              <cbc:ID>{escape(item.tax.category_code)}</cbc:ID>
              <cbc:Percent>{tax_rate}</cbc:Percent>
            </cac:ClassifiedTaxCategory>
          </cac:Item>
          <cac:Price>
            <cbc:PriceAmount currencyID="{currency}">{unit_price}</cbc:PriceAmount>
          </cac:Price>
        </cac:InvoiceLine>
        """
    ).strip()


def build_xrechnung_xml(invoice: Invoice, profile: TenantProfile, now: datetime) -> bytes:
    if not invoice.invoice_no:
        raise ValueError("Invoice number must be set before generating XRechnung")

    totals = invoice.compute_totals()
    now_str = _format_datetime(now)
    issue_date = invoice.issue_date.isoformat()
    due_date = invoice.due_date.isoformat()

    line_fragments = [
        _render_invoice_line(idx + 1, item, invoice.currency)
        for idx, item in enumerate(invoice.line_items)
    ]
    lines_xml = "\n".join(line_fragments)

    tax_totals = _aggregate_tax_items(invoice.line_items)
    tax_subtotal_fragments = []
    for rate in sorted(tax_totals.keys()):
        bucket = tax_totals[rate]
        tax_subtotal_fragments.append(
            textwrap.dedent(
                f"""
                <cac:TaxSubtotal>
                  <cbc:TaxableAmount currencyID="{invoice.currency}">{_format_decimal(bucket['net'])}</cbc:TaxableAmount>
                  <cbc:TaxAmount currencyID="{invoice.currency}">{_format_decimal(bucket['tax'])}</cbc:TaxAmount>
                  <cac:TaxCategory>
                    <cbc:ID>{escape('S')}</cbc:ID>
                    <cbc:Percent>{_format_decimal(rate)}</cbc:Percent>
                  </cac:TaxCategory>
                </cac:TaxSubtotal>
                """
            ).strip()
        )
    tax_subtotals_xml = "\n".join(tax_subtotal_fragments)

    xml_content = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Invoice xmlns=\"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2\"
         xmlns:cac=\"urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2\"
         xmlns:cbc=\"urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2\">
  <cbc:CustomizationID>{XRECHNUNG_CUSTOMIZATION_ID}</cbc:CustomizationID>
  <cbc:ProfileID>{XRECHNUNG_PROFILE_ID}</cbc:ProfileID>
  <cbc:ID>{escape(invoice.invoice_no)}</cbc:ID>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:DueDate>{due_date}</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>{escape(invoice.currency)}</cbc:DocumentCurrencyCode>
  <cbc:TaxCurrencyCode>{escape(invoice.currency)}</cbc:TaxCurrencyCode>
  <cbc:Note>Generated {now_str}</cbc:Note>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cbc:Name>{escape(profile.seller.name)}</cbc:Name>
      <cac:PostalAddress>
        <cbc:StreetName>{escape(profile.seller.address.street)}</cbc:StreetName>
        <cbc:CityName>{escape(profile.seller.address.city)}</cbc:CityName>
        <cbc:PostalZone>{escape(profile.seller.address.postal_code)}</cbc:PostalZone>
        <cac:Country>
          <cbc:IdentificationCode>{escape(profile.seller.address.country_code)}</cbc:IdentificationCode>
        </cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>{escape(profile.seller.vat_id or '')}</cbc:CompanyID>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{escape(profile.seller.name)}</cbc:RegistrationName>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cbc:Name>{escape(invoice.buyer.name)}</cbc:Name>
      <cac:PostalAddress>
        <cbc:StreetName>{escape(invoice.buyer.address.street)}</cbc:StreetName>
        <cbc:CityName>{escape(invoice.buyer.address.city)}</cbc:CityName>
        <cbc:PostalZone>{escape(invoice.buyer.address.postal_code)}</cbc:PostalZone>
        <cac:Country>
          <cbc:IdentificationCode>{escape(invoice.buyer.address.country_code)}</cbc:IdentificationCode>
        </cac:Country>
      </cac:PostalAddress>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:PaymentTerms>
    <cbc:Note>{escape(invoice.payment_terms)}</cbc:Note>
  </cac:PaymentTerms>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{invoice.currency}">{_format_decimal(totals.total_tax)}</cbc:TaxAmount>
{textwrap.indent(tax_subtotals_xml, '    ')}
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{invoice.currency}">{_format_decimal(totals.total_net)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{invoice.currency}">{_format_decimal(totals.total_net)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{invoice.currency}">{_format_decimal(totals.total_gross)}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{invoice.currency}">{_format_decimal(totals.total_gross)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
{textwrap.indent(lines_xml, '  ')}
</Invoice>
"""

    return xml_content.encode("utf-8")


def build_xrechnung_document(
    invoice: Invoice,
    profile: TenantProfile,
    now: datetime,
) -> bytes:
    return build_xrechnung_xml(invoice, profile, now)

