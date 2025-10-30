"""Offline-Validator (TEMP_VALIDATOR/OFFICIAL) für XRechnung-UBL."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List
from xml.etree import ElementTree as ET

from .generator import GENERATOR_VERSION, XRECHNUNG_CUSTOMIZATION_ID

try:
    from lxml import etree
    from lxml.isoschematron import Schematron
except ImportError:
    etree = None
    Schematron = None


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
        # Prüfe auf vorhandene XSD/Schematron-Dateien im official-Verzeichnis
        official_xsd_files = list(OFFICIAL_DIR.glob("*.xsd")) if OFFICIAL_DIR.exists() else []
        official_sch_files = list(OFFICIAL_DIR.glob("*.sch")) if OFFICIAL_DIR.exists() else []
        
        if not official_xsd_files or not official_sch_files:
            return "temp"  # Fallback zu TEMP wenn Ressourcen fehlen
    
    return mode


def _validate_with_official(xml_bytes: bytes) -> XRechnungValidationResult:
    """Validiert mit offiziellen XSD/Schematron-Ressourcen via lxml."""
    messages: List[str] = []
    
    if etree is None:
        messages.append("OFFICIAL_VALIDATOR: lxml not available, falling back to TEMP")
        return _validate_with_temp(xml_bytes)
    
    # Lade offizielle Ressourcen
    official_xsd_files = list(OFFICIAL_DIR.glob("*.xsd"))
    official_sch_files = list(OFFICIAL_DIR.glob("*.sch"))
    
    if not official_xsd_files:
        messages.append("OFFICIAL_VALIDATOR: No XSD files found in official/ directory")
        return _validate_with_temp(xml_bytes)
    
    schema_ok = False
    schematron_ok = False
    
    try:
        # Parse XML
        try:
            xml_doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as err:
            messages.append(f"OFFICIAL_VALIDATOR: XML parse error – {err}")
            return XRechnungValidationResult(False, False, messages)
        
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
        
        # Schematron-Validierung (erste Schematron-Datei verwenden)
        if official_sch_files:
            try:
                schematron_doc = etree.parse(str(official_sch_files[0]))
                schematron = Schematron(schematron_doc)
                schematron_ok = schematron.validate(xml_doc)
                if schematron_ok:
                    messages.append(f"OFFICIAL_VALIDATOR: Schematron validation OK ({official_sch_files[0].name})")
                else:
                    error_log = schematron.error_log
                    messages.append(f"OFFICIAL_VALIDATOR: Schematron validation failed: {error_log.last_error}")
            except Exception as err:  # noqa: BLE001
                messages.append(f"OFFICIAL_VALIDATOR: Schematron validation error – {err}")
                schematron_ok = False
        else:
            messages.append("OFFICIAL_VALIDATOR: No Schematron files found, skipping Schematron validation")
            schematron_ok = True  # Nicht verfügbar, aber kein Fehler
        
        return XRechnungValidationResult(schema_ok, schematron_ok, messages)
    
    except Exception as err:  # noqa: BLE001
        messages.append(f"OFFICIAL_VALIDATOR: Unexpected error – {err}")
        return XRechnungValidationResult(False, False, messages)


def _validate_with_temp(xml_bytes: bytes) -> XRechnungValidationResult:
    """Validiert mit TEMP-Stub-Logik (bestehende Implementierung)."""
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


def validate_xrechnung(xml_bytes: bytes) -> XRechnungValidationResult:
    """Validiert XRechnung-XML basierend auf konfiguriertem Modus (OFFICIAL/TEMP)."""
    mode = _get_validation_mode()
    
    if mode == "official":
        return _validate_with_official(xml_bytes)
    else:
        return _validate_with_temp(xml_bytes)

