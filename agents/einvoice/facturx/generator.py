"""Factur-X Generator (A2) – TEMP_PDF_A_WRITER Stub.

Dieses Modul stellt eine deterministische, rein in-memory arbeitende
Placeholder-Implementierung für die Factur-X (ZUGFeRD Comfort) Erzeugung zur
Verfügung. Die generierte XML folgt einem stark vereinfachten Schema, das auf
den im Projekt hinterlegten Beispielrechnungen basiert. Die PDF/A-3-Erzeugung
nutzt einen stubhaften Writer, der die XML-Daten Base64-kodiert einbettet und
mit dem Marker ``TEMP_PDF_A_WRITER`` versehen ist. Dadurch können spätere
Iterationen den Stub gezielt durch einen echten PDF/A-Writer ersetzen, ohne die
Tests in A2 zu verändern.
"""

from __future__ import annotations

import base64
import hashlib
import textwrap
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from typing import Iterable, Optional

from agents.einvoice.dto import Invoice, LineItem
from agents.einvoice.stammdaten import TenantProfile

FACTURX_COMFORT_GUIDELINE = "urn:cen.eu:en16931:2017#compliant#factur-x.comfort"
TEMP_PDF_MARKER = "TEMP_PDF_A_WRITER"
GENERATOR_VERSION = "TEMP_PDF_A_WRITER-0.1.0"


def version() -> str:
    """Gibt die Generator-Version zurück."""

    return GENERATOR_VERSION


def _format_decimal(value: Decimal) -> str:
    return f"{value:.2f}"


def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _render_trade_line(index: int, item: LineItem) -> str:
    net_amount = item.net_amount()
    tax_amount = item.tax_amount()
    gross_amount = item.gross_amount()
    return textwrap.dedent(
        f"""
        <IncludedSupplyChainTradeLineItem>
          <AssociatedDocumentLineDocument>
            <LineID>{index}</LineID>
            <LineStatus>final</LineStatus>
          </AssociatedDocumentLineDocument>
          <SpecifiedTradeProduct>
            <Name>{escape(item.description)}</Name>
          </SpecifiedTradeProduct>
          <SpecifiedLineTradeAgreement>
            <NetPriceProductTradePrice>
              <ChargeAmount>{_format_decimal(item.unit_price)}</ChargeAmount>
            </NetPriceProductTradePrice>
          </SpecifiedLineTradeAgreement>
          <SpecifiedLineTradeDelivery>
            <BilledQuantity>{_format_decimal(item.quantity)}</BilledQuantity>
          </SpecifiedLineTradeDelivery>
          <SpecifiedLineTradeSettlement>
            <ApplicableTradeTax>
              <TypeCode>VAT</TypeCode>
              <CategoryCode>{escape(item.tax.category_code)}</CategoryCode>
              <RateApplicablePercent>{_format_decimal(item.tax.rate)}</RateApplicablePercent>
            </ApplicableTradeTax>
            <SpecifiedTradeSettlementLineMonetarySummation>
              <LineTotalAmount>{_format_decimal(net_amount)}</LineTotalAmount>
              <TaxTotalAmount>{_format_decimal(tax_amount)}</TaxTotalAmount>
              <GrandTotalAmount>{_format_decimal(gross_amount)}</GrandTotalAmount>
            </SpecifiedTradeSettlementLineMonetarySummation>
          </SpecifiedLineTradeSettlement>
        </IncludedSupplyChainTradeLineItem>
        """
    ).strip()


def _aggregate_tax_items(line_items: Iterable[LineItem]) -> dict[Decimal, dict[str, Decimal]]:
    totals: dict[Decimal, dict[str, Decimal]] = {}
    for item in line_items:
        rate = item.tax.rate
        agg = totals.setdefault(rate, {"net": Decimal("0.00"), "tax": Decimal("0.00")})
        agg["net"] += item.net_amount()
        agg["tax"] += item.tax_amount()
    return totals


def _render_tax_totals(line_items: Iterable[LineItem]) -> str:
    aggregates = _aggregate_tax_items(line_items)
    fragments = []
    for rate in sorted(aggregates.keys()):
        agg = aggregates[rate]
        fragments.append(
            textwrap.dedent(
                f"""
                <TaxTotal>
                  <TaxAmount>{_format_decimal(agg['tax'])}</TaxAmount>
                  <TaxSubtotal>
                    <TaxableAmount>{_format_decimal(agg['net'])}</TaxableAmount>
                    <TaxAmount>{_format_decimal(agg['tax'])}</TaxAmount>
                    <TaxCategory>
                      <Percent>{_format_decimal(rate)}</Percent>
                    </TaxCategory>
                  </TaxSubtotal>
                </TaxTotal>
                """
            ).strip()
        )
    return "\n".join(fragments)


def build_facturx_xml(invoice: Invoice, profile: TenantProfile, now: datetime) -> bytes:
    """Erzeugt eine vereinfachte Factur-X-konforme XML-Ausgabe.

    Die Funktion erwartet, dass ``invoice.invoice_no`` bereits gesetzt ist und
    dass ``invoice.validate()`` erfolgreich war. Die Ausgabe ist deterministisch
    und basiert ausschließlich auf den übergebenen Daten.
    """

    if not invoice.invoice_no:
        raise ValueError("Invoice number must be set before generating Factur-X XML")

    invoice_totals = invoice.compute_totals()
    now_str = _format_datetime(now)
    issue_date = invoice.issue_date.isoformat()
    due_date = invoice.due_date.isoformat()

    lines_xml = "\n".join(
        _render_trade_line(idx + 1, item) for idx, item in enumerate(invoice.line_items)
    )
    tax_totals_xml = _render_tax_totals(invoice.line_items)

    xml_content = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<FacturX xmlns=\"urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#\">
  <DocumentContext>
    <Guideline>{FACTURX_COMFORT_GUIDELINE}</Guideline>
    <CreationTimestamp>{now_str}</CreationTimestamp>
    <GeneratorVersion>{GENERATOR_VERSION}</GeneratorVersion>
  </DocumentContext>
  <Header>
    <InvoiceNumber>{escape(invoice.invoice_no)}</InvoiceNumber>
    <InvoiceIssueDate>{issue_date}</InvoiceIssueDate>
    <InvoiceDueDate>{due_date}</InvoiceDueDate>
    <Currency>{escape(invoice.currency)}</Currency>
    <PaymentTerms>{escape(invoice.payment_terms)}</PaymentTerms>
  </Header>
  <Seller>
    <Name>{escape(profile.seller.name)}</Name>
    <Street>{escape(profile.seller.address.street)}</Street>
    <PostalCode>{escape(profile.seller.address.postal_code)}</PostalCode>
    <City>{escape(profile.seller.address.city)}</City>
    <Country>{escape(profile.seller.address.country_code)}</Country>
    <VatId>{escape(profile.seller.vat_id or "")}</VatId>
    <Iban>{escape(profile.seller.iban or "")}</Iban>
  </Seller>
  <Buyer>
    <Name>{escape(invoice.buyer.name)}</Name>
    <Street>{escape(invoice.buyer.address.street)}</Street>
    <PostalCode>{escape(invoice.buyer.address.postal_code)}</PostalCode>
    <City>{escape(invoice.buyer.address.city)}</City>
    <Country>{escape(invoice.buyer.address.country_code)}</Country>
  </Buyer>
  <SupplyChainTradeLineItems>
{textwrap.indent(lines_xml, '    ')}
  </SupplyChainTradeLineItems>
  <Totals>
    <NetAmount>{_format_decimal(invoice_totals.total_net)}</NetAmount>
    <TaxAmount>{_format_decimal(invoice_totals.total_tax)}</TaxAmount>
    <GrossAmount>{_format_decimal(invoice_totals.total_gross)}</GrossAmount>
{textwrap.indent(tax_totals_xml, '    ')}
  </Totals>
</FacturX>
"""

    return xml_content.encode("utf-8")


def embed_xml_to_pdf(
    pdf_bytes: Optional[bytes],
    xml_bytes: bytes,
    invoice_no: str,
    *,
    timestamp: datetime,
) -> bytes:
    """Betten die XML (Base64) in ein deterministisches PDF/A-3-ähnliches Dokument ein.

    ``pdf_bytes`` wird aktuell ignoriert, dient jedoch als Platzhalter für
    künftige Erweiterungen, in denen ein echtes PDF-Template verwendet wird.
    """

    xml_sha256 = hashlib.sha256(xml_bytes).hexdigest()
    xml_base64 = base64.b64encode(xml_bytes).decode("ascii")
    timestamp_str = _format_datetime(timestamp)

    pdf_lines = [
        "%PDF-1.4",
        f"%{TEMP_PDF_MARKER}",
        f"%INVOICE:{invoice_no}",
        f"%XML-SHA256:{xml_sha256}",
        "1 0 obj<< /Type /Catalog /Producer (" + TEMP_PDF_MARKER + ") >>endobj",
        "2 0 obj<< /Type /Metadata /Subtype /XML >>stream",
        xml_base64,
        "endstream endobj",
        (
            "3 0 obj<< /Type /EmbeddedFile /Params << /ModDate ("
            + timestamp_str
            + ") >> /Length "
            + str(len(xml_bytes))
            + " /Checksum ("
            + xml_sha256
            + ") >>stream"
        ),
        xml_base64,
        "endstream endobj",
        "trailer<< /Root 1 0 R >>",
        "%%EOF",
    ]
    return "\n".join(pdf_lines).encode("ascii")


def build_facturx_document(
    invoice: Invoice,
    profile: TenantProfile,
    now: datetime,
    pdf_template_bytes: Optional[bytes] = None,
) -> tuple[bytes, bytes]:
    """Erzeugt PDF- und XML-Bytes für den übergebenen Invoice-Datensatz."""

    xml_bytes = build_facturx_xml(invoice, profile, now)
    pdf_bytes = embed_xml_to_pdf(
        pdf_template_bytes,
        xml_bytes,
        invoice.invoice_no or "",
        timestamp=now,
    )
    return pdf_bytes, xml_bytes

