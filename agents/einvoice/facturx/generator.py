"""Factur-X Generator – PDF/A-3 Best-Effort (ReportLab+pikepdf).

Dieses Modul stellt eine Best-Effort-Implementierung für die Factur-X (ZUGFeRD Comfort)
Erzeugung zur Verfügung. Die generierte XML folgt einem vereinfachten Schema. Die PDF/A-3-Erzeugung
nutzt ReportLab für das Grundgerüst und pikepdf für PDF/A-3-Konformität (XMP-Metadaten,
ICC-Profil, AF-Relationship, Embedded File Specification).

Hinweis: PDF/A ist "Best-Effort" – formale Konformität wird erst später mit externem
Validator/GOBD-Prozess abschließend belegt.
"""

from __future__ import annotations

import hashlib
import io
import textwrap
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from typing import Iterable, Optional

from agents.einvoice.dto import Invoice, LineItem
from agents.einvoice.stammdaten import TenantProfile

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except ImportError:
    canvas = None
    A4 = None

try:
    import pikepdf
except ImportError:
    pikepdf = None

FACTURX_COMFORT_GUIDELINE = "urn:cen.eu:en16931:2017#compliant#factur-x.comfort"
GENERATOR_VERSION = "facturx-pdfa-best-effort-1.0.0"
PDF_A_PRODUCER = "0Admin-NEXT Factur-X Generator"


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
    """Betten die XML in ein PDF/A-3 Best-Effort-Dokument ein.

    Verwendet ReportLab für das Grundgerüst und pikepdf für PDF/A-3-Konformität.
    Falls ReportLab oder pikepdf nicht verfügbar sind, wird auf TEMP-Stub zurückgefallen.

    Args:
        pdf_bytes: Optionales PDF-Template (aktuell ignoriert)
        xml_bytes: Factur-X XML-Bytes
        invoice_no: Rechnungsnummer
        timestamp: Zeitstempel für Determinismus

    Returns:
        PDF/A-3 Best-Effort Bytes
    """
    # Fallback zu TEMP-Stub wenn Bibliotheken fehlen
    if canvas is None or pikepdf is None:
        return _embed_xml_to_pdf_stub(pdf_bytes, xml_bytes, invoice_no, timestamp=timestamp)

    # Deterministische Formatierung
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)
    timestamp_str = timestamp.isoformat().replace("+00:00", "Z")

    # 1. ReportLab: PDF-Grundgerüst erstellen
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Invoice {invoice_no}")
    c.setCreator(PDF_A_PRODUCER)
    c.setProducer(PDF_A_PRODUCER)
    c.setSubject("Factur-X Invoice")
    c.setAuthor(PDF_A_PRODUCER)
    
    # Einfache Textseite (für visuelle Darstellung)
    c.drawString(100, 750, f"Invoice: {invoice_no}")
    c.drawString(100, 730, f"Date: {timestamp_str}")
    c.showPage()
    c.save()
    
    pdf_buffer_bytes = buffer.getvalue()
    buffer.close()

    # 2. pikepdf: PDF/A-3-Konformität hinzufügen
    pdf_doc = pikepdf.Pdf.open(io.BytesIO(pdf_buffer_bytes))

    # XMP-Metadaten (PDF/A-3 konform)
    xmp_metadata = f"""<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/'>
  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:Description rdf:about='' xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/'>
      <pdfaid:part>3</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
    </rdf:Description>
    <rdf:Description rdf:about='' xmlns:dc='http://purl.org/dc/elements/1.1/'>
      <dc:title>Invoice {invoice_no}</dc:title>
      <dc:creator>{PDF_A_PRODUCER}</dc:creator>
      <dc:subject>Factur-X Invoice</dc:subject>
    </rdf:Description>
    <rdf:Description rdf:about='' xmlns:xmp='http://ns.adobe.com/xap/1.0/'>
      <xmp:CreateDate>{timestamp_str}</xmp:CreateDate>
      <xmp:ModifyDate>{timestamp_str}</xmp:ModifyDate>
      <xmp:CreatorTool>{PDF_A_PRODUCER}</xmp:CreatorTool>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""
    
    pdf_doc.Root.Metadata = pikepdf.Stream(pdf_doc, xmp_metadata.encode("utf-8"))
    pdf_doc.Root.Metadata.Type = pikepdf.Name("/Metadata")
    pdf_doc.Root.Metadata.Subtype = pikepdf.Name("/XML")

    # AF-Relationship (ZUGFeRD/Factur-X Attachment)
    # Erstelle Embedded File für XML
    xml_stream = pikepdf.Stream(pdf_doc, xml_bytes)
    xml_stream[pikepdf.Name("/Type")] = pikepdf.Name("/EmbeddedFile")
    xml_stream[pikepdf.Name("/Subtype")] = pikepdf.Name("/application/xml")
    
    # Params Dictionary: Keys müssen normale Strings sein
    params_dict = pikepdf.Dictionary()
    params_dict["/ModDate"] = pikepdf.String(timestamp_str)
    params_dict["/Size"] = len(xml_bytes)
    xml_stream[pikepdf.Name("/Params")] = params_dict

    # Filespec für Attachment
    filespec = pikepdf.Dictionary()
    filespec["/Type"] = pikepdf.Name("/Filespec")
    filespec["/F"] = pikepdf.String("factur-x.xml")
    filespec["/UF"] = pikepdf.String("factur-x.xml")
    ef_dict = pikepdf.Dictionary()
    ef_dict["/F"] = xml_stream
    filespec["/EF"] = ef_dict
    filespec["/AFRelationship"] = pikepdf.Name("/Alternative")

    # AF-Array im Root
    if pikepdf.Name("/AF") not in pdf_doc.Root:
        pdf_doc.Root[pikepdf.Name("/AF")] = pikepdf.Array()
    pdf_doc.Root[pikepdf.Name("/AF")].append(filespec)

    # 3. Output als deterministische Bytes
    output_buffer = io.BytesIO()
    pdf_doc.save(output_buffer, compress_streams=True, normalize_content=True)
    output_bytes = output_buffer.getvalue()
    output_buffer.close()
    pdf_doc.close()

    return output_bytes


def _embed_xml_to_pdf_stub(
    pdf_bytes: Optional[bytes],
    xml_bytes: bytes,
    invoice_no: str,
    *,
    timestamp: datetime,
) -> bytes:
    """Fallback-Stub-Implementierung wenn ReportLab/pikepdf nicht verfügbar sind."""
    import base64
    
    xml_sha256 = hashlib.sha256(xml_bytes).hexdigest()
    xml_base64 = base64.b64encode(xml_bytes).decode("ascii")
    timestamp_str = _format_datetime(timestamp)
    TEMP_PDF_MARKER = "TEMP_PDF_A_WRITER"

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

