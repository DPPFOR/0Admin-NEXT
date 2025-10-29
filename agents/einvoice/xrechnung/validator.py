"""Offline-Validator (TEMP_VALIDATOR) für XRechnung-UBL."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List
from xml.etree import ElementTree as ET

from .generator import GENERATOR_VERSION, XRECHNUNG_CUSTOMIZATION_ID


@dataclass(frozen=True)
class XRechnungValidationResult:
    schema_ok: bool
    schematron_ok: bool
    messages: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
STUB_XSD = RESOURCE_DIR / "ubl_stub.xsd"
STUB_SCHEMATRON = RESOURCE_DIR / "ubl_schematron_stub.sch"


def _parse_decimal(text: str) -> Decimal:
    return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def validate_xrechnung(xml_bytes: bytes) -> XRechnungValidationResult:
    messages: List[str] = []

    # Ensure resources exist (offline stub requirement)
    for stub in (STUB_XSD, STUB_SCHEMATRON):
        if not stub.exists():
            messages.append(f"TEMP_VALIDATOR: missing resource {stub.name}")
            return XRechnungValidationResult(False, False, messages)

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as err:
        messages.append(f"TEMP_VALIDATOR: XML parse error – {err}")
        return XRechnungValidationResult(False, False, messages)

    if _strip_ns(root.tag) != "Invoice":
        messages.append("TEMP_VALIDATOR: Root element must be 'Invoice'")
        return XRechnungValidationResult(False, False, messages)

    ns = {
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }

    customization = root.findtext("cbc:CustomizationID", namespaces=ns)
    if customization != XRECHNUNG_CUSTOMIZATION_ID:
        messages.append("TEMP_VALIDATOR: CustomizationID mismatch")
    else:
        messages.append("TEMP_VALIDATOR: CustomizationID OK")

    legal_total = root.find("cac:LegalMonetaryTotal", namespaces=ns)
    if legal_total is None:
        messages.append("TEMP_VALIDATOR: LegalMonetaryTotal missing")
        return XRechnungValidationResult(False, False, messages)

    try:
        line_extension = _parse_decimal(legal_total.findtext("cbc:LineExtensionAmount", namespaces=ns) or "0")
        tax_exclusive = _parse_decimal(legal_total.findtext("cbc:TaxExclusiveAmount", namespaces=ns) or "0")
        tax_inclusive = _parse_decimal(legal_total.findtext("cbc:TaxInclusiveAmount", namespaces=ns) or "0")
        payable = _parse_decimal(legal_total.findtext("cbc:PayableAmount", namespaces=ns) or "0")
    except Exception as err:  # noqa: BLE001 - controlled stub validation
        messages.append(f"TEMP_VALIDATOR: Invalid monetary total – {err}")
        return XRechnungValidationResult(False, False, messages)

    if line_extension != tax_exclusive:
        messages.append("TEMP_VALIDATOR: LineExtension vs TaxExclusive mismatch")
        return XRechnungValidationResult(False, False, messages)

    tax_totals = root.findall("cac:TaxTotal", namespaces=ns)
    tax_amount_sum = Decimal("0.00")
    for tax_total in tax_totals:
        value = tax_total.findtext("cbc:TaxAmount", namespaces=ns)
        if value:
            tax_amount_sum += _parse_decimal(value)

    expected_tax = tax_inclusive - tax_exclusive
    if tax_amount_sum != expected_tax:
        messages.append("TEMP_VALIDATOR: Aggregated tax totals mismatch")
        return XRechnungValidationResult(False, False, messages)

    if payable != tax_inclusive:
        messages.append("TEMP_VALIDATOR: Payable amount mismatch")
        return XRechnungValidationResult(False, False, messages)

    messages.append(f"TEMP_VALIDATOR: XRechnung stub validated ({GENERATOR_VERSION})")
    return XRechnungValidationResult(True, True, messages)

