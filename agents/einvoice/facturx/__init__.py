"""Factur-X Hilfsmodule (A2) – Generator, Validator und Ressourcen."""

from .generator import (
    FACTURX_COMFORT_GUIDELINE,
    build_facturx_document,
    build_facturx_xml,
    embed_xml_to_pdf,
    version,
)
from .validator import FacturXValidationResult, validate_facturx

__all__ = [
    "FACTURX_COMFORT_GUIDELINE",
    "build_facturx_document",
    "build_facturx_xml",
    "embed_xml_to_pdf",
    "version",
    "FacturXValidationResult",
    "validate_facturx",
]

