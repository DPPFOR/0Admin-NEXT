"""EN16931 Kernkomponenten (A1) für Rechnungs-DTOs und Nummernkreis."""

from .archive import write_package
from .approval import approve, reject
from .dto import Address, Invoice, LineItem, Party, Tax, Totals
from .facturx import (
    FACTURX_COMFORT_GUIDELINE,
    FacturXValidationResult,
    build_facturx_document,
    build_facturx_xml,
    embed_xml_to_pdf,
    validate_facturx,
    version as facturx_version,
)
from .numbering import NumberingService
from .samples import (
    BUYER_PARTY,
    SCENARIOS,
    SELLER_PARTY,
    SampleScenario,
    build_sample_invoice,
    build_sample_profile,
    iter_sample_scenarios,
)
from .xrechnung import (
    XRECHNUNG_CUSTOMIZATION_ID,
    XRECHNUNG_PROFILE_ID,
    XRechnungValidationResult,
    build_xrechnung_document,
    build_xrechnung_xml,
    validate_xrechnung,
    version as xrechnung_version,
)
from .stammdaten import TenantProfile, TenantProfileProvider

version = facturx_version

__all__ = [
    "write_package",
    "approve",
    "reject",
    "Address",
    "Invoice",
    "LineItem",
    "Party",
    "Tax",
    "Totals",
    "NumberingService",
    "TenantProfile",
    "TenantProfileProvider",
    "FACTURX_COMFORT_GUIDELINE",
    "FacturXValidationResult",
    "build_facturx_document",
    "build_facturx_xml",
    "embed_xml_to_pdf",
    "validate_facturx",
    "facturx_version",
    "version",
    "XRECHNUNG_CUSTOMIZATION_ID",
    "XRECHNUNG_PROFILE_ID",
    "XRechnungValidationResult",
    "build_xrechnung_document",
    "build_xrechnung_xml",
    "validate_xrechnung",
    "xrechnung_version",
    "SCENARIOS",
    "SampleScenario",
    "SELLER_PARTY",
    "BUYER_PARTY",
    "iter_sample_scenarios",
    "build_sample_invoice",
    "build_sample_profile",
]

