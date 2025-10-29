"""Offline-Validator (TEMP_VALIDATOR) für Factur-X-Stubs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List
from xml.etree import ElementTree as ET

from .generator import FACTURX_COMFORT_GUIDELINE


@dataclass(frozen=True)
class FacturXValidationResult:
    schema_ok: bool
    schematron_ok: bool
    messages: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _parse_decimal(text: str) -> Decimal:
    return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def validate_facturx(xml_bytes: bytes) -> FacturXValidationResult:
    messages: List[str] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as err:
        messages.append(f"TEMP_VALIDATOR: XML parse error – {err}")
        return FacturXValidationResult(False, False, messages)

    if _strip_ns(root.tag) != "FacturX":
        messages.append("TEMP_VALIDATOR: Root element must be 'FacturX'")
        return FacturXValidationResult(False, False, messages)

    guideline = root.findtext("./{*}DocumentContext/{*}Guideline")
    if guideline != FACTURX_COMFORT_GUIDELINE:
        messages.append("TEMP_VALIDATOR: Guideline mismatch")
    else:
        messages.append("TEMP_VALIDATOR: Guideline OK")

    totals_node = root.find("./{*}Totals")
    if totals_node is None:
        messages.append("TEMP_VALIDATOR: Totals section missing")
        return FacturXValidationResult(False, False, messages)

    try:
        net_amount = _parse_decimal(totals_node.findtext("./{*}NetAmount", "0"))
        tax_amount = _parse_decimal(totals_node.findtext("./{*}TaxAmount", "0"))
        gross_amount = _parse_decimal(totals_node.findtext("./{*}GrossAmount", "0"))
    except Exception as err:  # noqa: BLE001 - kontrollierte Placeholder-Validierung
        messages.append(f"TEMP_VALIDATOR: Invalid totals – {err}")
        return FacturXValidationResult(False, False, messages)

    if net_amount + tax_amount != gross_amount:
        messages.append("TEMP_VALIDATOR: Net + Tax must equal Gross")
        return FacturXValidationResult(False, False, messages)

    # Prüfe TaxTotal-Summen (einfacher Abgleich)
    sum_tax = Decimal("0.00")
    for node in totals_node.findall("./{*}TaxTotal"):
        subtotal_tax = _parse_decimal(node.findtext("./{*}TaxAmount", "0"))
        sum_tax += subtotal_tax

    if sum_tax != tax_amount:
        messages.append("TEMP_VALIDATOR: Aggregated tax totals mismatch")
        return FacturXValidationResult(False, False, messages)

    return FacturXValidationResult(True, True, messages)

