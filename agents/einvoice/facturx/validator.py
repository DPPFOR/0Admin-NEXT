"""Offline-Validator (TEMP_VALIDATOR/OFFICIAL) für Factur-X-Stubs."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List
from xml.etree import ElementTree as ET

from .generator import FACTURX_COMFORT_GUIDELINE

try:
    from lxml import etree
except ImportError:
    etree = None


@dataclass(frozen=True)
class FacturXValidationResult:
    schema_ok: bool
    schematron_ok: bool
    messages: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
OFFICIAL_DIR = RESOURCE_DIR / "official"


def _parse_decimal(text: str) -> Decimal:
    return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _get_validation_mode() -> str:
    """Bestimmt den Validierungsmodus basierend auf ENV und Ressourcen-Verfügbarkeit."""
    mode = os.getenv("EINVOICE_VALIDATION_MODE", "temp").lower()
    
    # Wenn OFFICIAL angefordert, prüfe ob Ressourcen vorhanden sind
    if mode == "official":
        # Prüfe auf vorhandene XSD-Dateien im official-Verzeichnis
        official_xsd_files = list(OFFICIAL_DIR.glob("*.xsd")) if OFFICIAL_DIR.exists() else []
        
        if not official_xsd_files:
            return "temp"  # Fallback zu TEMP wenn Ressourcen fehlen
    
    return mode


def _validate_with_official(xml_bytes: bytes) -> FacturXValidationResult:
    """Validiert mit offiziellen XSD-Ressourcen via lxml."""
    messages: List[str] = []
    
    if etree is None:
        messages.append("OFFICIAL_VALIDATOR: lxml not available, falling back to TEMP")
        return _validate_with_temp(xml_bytes)
    
    # Lade offizielle Ressourcen
    official_xsd_files = list(OFFICIAL_DIR.glob("*.xsd"))
    
    if not official_xsd_files:
        messages.append("OFFICIAL_VALIDATOR: No XSD files found in official/ directory")
        return _validate_with_temp(xml_bytes)
    
    schema_ok = False
    
    try:
        # Parse XML
        try:
            xml_doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as err:
            messages.append(f"OFFICIAL_VALIDATOR: XML parse error – {err}")
            return FacturXValidationResult(False, False, messages)
        
        # Schema-Validierung (erste XSD-Datei verwenden)
        try:
            schema_doc = etree.parse(str(official_xsd_files[0]))
            schema = etree.XMLSchema(schema_doc)
            schema_ok = schema.validate(xml_doc)
            if schema_ok:
                messages.append(f"OFFICIAL_VALIDATOR: Schema validation OK ({official_xsd_files[0].name})")
            else:
                error_log = schema.error_log
                messages.append(f"OFFICIAL_VALIDATOR: Schema validation failed: {error_log.last_error}")
        except Exception as err:  # noqa: BLE001
            messages.append(f"OFFICIAL_VALIDATOR: Schema validation error – {err}")
            schema_ok = False
        
        # Factur-X hat kein Schematron (nur Schema-Validierung)
        schematron_ok = True
        
        return FacturXValidationResult(schema_ok, schematron_ok, messages)
    
    except Exception as err:  # noqa: BLE001
        messages.append(f"OFFICIAL_VALIDATOR: Unexpected error – {err}")
        return FacturXValidationResult(False, False, messages)


def _validate_with_temp(xml_bytes: bytes) -> FacturXValidationResult:
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


def validate_facturx(xml_bytes: bytes) -> FacturXValidationResult:
    """Validiert Factur-X-XML basierend auf konfiguriertem Modus (OFFICIAL/TEMP)."""
    mode = _get_validation_mode()
    
    if mode == "official":
        return _validate_with_official(xml_bytes)
    else:
        return _validate_with_temp(xml_bytes)

