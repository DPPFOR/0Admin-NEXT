"""Tests for Factur-X vs XRechnung parity — auto-generated via PDD."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from agents.einvoice import (
    NumberingService,
    build_facturx_document,
    build_sample_invoice,
    build_sample_profile,
    build_xrechnung_document,
    facturx_version,
    iter_sample_scenarios,
    validate_facturx,
    validate_xrechnung,
    xrechnung_version,
)


FX_NS = {"fx": "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"}
UBL_NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


def _extract_facturx_totals(xml_bytes: bytes) -> dict[str, Decimal]:
    root = ET.fromstring(xml_bytes)
    totals_node = root.find("fx:Totals", namespaces=FX_NS)
    assert totals_node is not None
    net = Decimal(totals_node.findtext("fx:NetAmount", namespaces=FX_NS))
    tax = Decimal(totals_node.findtext("fx:TaxAmount", namespaces=FX_NS))
    gross = Decimal(totals_node.findtext("fx:GrossAmount", namespaces=FX_NS))
    return {"net": net, "tax": tax, "gross": gross}


def _extract_xrechnung_totals(xml_bytes: bytes) -> dict[str, Decimal]:
    root = ET.fromstring(xml_bytes)
    legal_total = root.find("cac:LegalMonetaryTotal", namespaces=UBL_NS)
    assert legal_total is not None
    net = Decimal(legal_total.findtext("cbc:TaxExclusiveAmount", namespaces=UBL_NS))
    gross = Decimal(legal_total.findtext("cbc:TaxInclusiveAmount", namespaces=UBL_NS))
    tax = gross - net
    return {"net": net, "tax": tax, "gross": gross}


def _extract_facturx_parties(xml_bytes: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_bytes)
    seller = root.find("fx:Seller/fx:Name", namespaces=FX_NS).text
    buyer = root.find("fx:Buyer/fx:Name", namespaces=FX_NS).text
    payment_terms = root.find("fx:Header/fx:PaymentTerms", namespaces=FX_NS).text
    return {"seller": seller, "buyer": buyer, "payment_terms": payment_terms}


def _extract_xrechnung_parties(xml_bytes: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_bytes)
    seller = root.find("cac:AccountingSupplierParty/cac:Party/cbc:Name", namespaces=UBL_NS).text
    buyer = root.find("cac:AccountingCustomerParty/cac:Party/cbc:Name", namespaces=UBL_NS).text
    payment_terms = root.find("cac:PaymentTerms/cbc:Note", namespaces=UBL_NS).text
    return {"seller": seller, "buyer": buyer, "payment_terms": payment_terms}


@pytest.mark.parametrize("scenario", list(iter_sample_scenarios()), ids=lambda s: s.code)
def test_facturx_xrechnung_parity(scenario) -> None:
    profile = build_sample_profile("tenant-parity")
    invoice = build_sample_invoice(
        scenario,
        invoice_id=f"tenant-parity-{scenario.code}",
        tenant_id="tenant-parity",
        issue_date=datetime(2025, 1, 1, tzinfo=timezone.utc).date(),
        due_date=datetime(2025, 1, 15, tzinfo=timezone.utc).date(),
        payment_terms=profile.payment_terms,
        now_provider=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    numbering = NumberingService(clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc))
    reservation_id = numbering.reserve("tenant-parity", invoice.issue_date)
    invoice_no = numbering.commit(reservation_id)
    invoice.invoice_no = invoice_no

    facturx_pdf, facturx_xml = build_facturx_document(
        invoice,
        profile,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    xrechnung_xml = build_xrechnung_document(
        invoice,
        profile,
        datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    assert facturx_pdf  # ensure bytes exist

    validation_facturx = validate_facturx(facturx_xml)
    validation_xrechnung = validate_xrechnung(xrechnung_xml)
    assert validation_facturx.schema_ok
    assert validation_xrechnung.schema_ok

    fx_totals = _extract_facturx_totals(facturx_xml)
    xr_totals = _extract_xrechnung_totals(xrechnung_xml)
    assert fx_totals == xr_totals

    fx_parties = _extract_facturx_parties(facturx_xml)
    xr_parties = _extract_xrechnung_parties(xrechnung_xml)
    assert fx_parties == xr_parties

    assert facturx_version()
    assert xrechnung_version()

    facturx_key = invoice.idempotency_key(invoice_no, "facturx")
    xrechnung_key = invoice.idempotency_key(invoice_no, "xrechnung-ubl")
    assert facturx_key != xrechnung_key
    assert xrechnung_key.endswith("|xrechnung-ubl")

