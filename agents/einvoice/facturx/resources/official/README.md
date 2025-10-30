# Offizielle Factur-X/ZUGFeRD Validator-Ressourcen

Dieses Verzeichnis enthält die offiziellen XSD-Dateien für die Factur-X/ZUGFeRD-Validierung.

## Quellen

Die offiziellen Ressourcen müssen manuell abgelegt werden:

1. **EN16931 XSD**: Von der offiziellen Factur-X-Website (z.B. https://www.factur-x.eu/)
2. **ZUGFeRD XSD**: Von der offiziellen ZUGFeRD-Dokumentation

## Erwartete Dateien

- `EN16931.xsd` (EN16931 Cross Industry Invoice Schema)
- `factur-x.xsd` (Factur-X/ZUGFeRD-spezifische Schemas)

## Verwendung

Der Validator (`agents/einvoice/facturx/validator.py`) verwendet diese Ressourcen automatisch, wenn:
- `EINVOICE_VALIDATION_MODE=official` gesetzt ist UND
- Die Ressourcen im `official/` Verzeichnis vorhanden sind

Falls die Ressourcen fehlen oder `EINVOICE_VALIDATION_MODE=temp` gesetzt ist, wird automatisch auf den TEMP-Mode (Stub-Validierung) zurückgefallen.

