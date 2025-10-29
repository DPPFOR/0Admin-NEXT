"""XRechnung (UBL) Generator und Validator Stubs für A3."""

from .generator import (
    XRECHNUNG_CUSTOMIZATION_ID,
    XRECHNUNG_PROFILE_ID,
    build_xrechnung_document,
    build_xrechnung_xml,
    version,
)
from .validator import XRechnungValidationResult, validate_xrechnung

__all__ = [
    "XRECHNUNG_CUSTOMIZATION_ID",
    "XRECHNUNG_PROFILE_ID",
    "build_xrechnung_document",
    "build_xrechnung_xml",
    "version",
    "XRechnungValidationResult",
    "validate_xrechnung",
]

