# Offizielle XRechnung Validator-Ressourcen

Dieses Verzeichnis enthält die offiziellen XSD- und Schematron-Dateien für die XRechnung-UBL-Validierung.

## Quellen

Die offiziellen Ressourcen müssen manuell abgelegt werden:

1. **XRechnung UBL XSD**: Von der offiziellen XRechnung-Website (z.B. https://www.xrechnung.org/)
2. **XRechnung Schematron**: Von der offiziellen XRechnung-Website

## Erwartete Dateien

- `xrechnung_ubl.xsd` (oder entsprechende UBL-XSD-Dateien)
- `xrechnung_schematron.sch` (Schematron-Regeln)

## Verwendung

Der Validator (`agents/einvoice/xrechnung/validator.py`) verwendet diese Ressourcen automatisch, wenn:
- `EINVOICE_VALIDATION_MODE=official` gesetzt ist UND
- Die Ressourcen im `official/` Verzeichnis vorhanden sind

Falls die Ressourcen fehlen oder `EINVOICE_VALIDATION_MODE=temp` gesetzt ist, wird automatisch auf den TEMP-Mode (Stub-Validierung) zurückgefallen.

