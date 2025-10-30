# E-Invoice Hardening & Operate Dokumentation

## Zweck

Diese Dokumentation beschreibt die Hardening-Maßnahmen und Operate-Runbooks für das E-Rechnung-Modul.

## Validator-Ressourcen

### Offizielle XSD/Schematron-Dateien

Die offiziellen Validator-Ressourcen müssen manuell in folgende Verzeichnisse abgelegt werden:

- **XRechnung**: `agents/einvoice/xrechnung/resources/official/`
  - Erwartete Dateien: `*.xsd` (UBL/XRechnung XSD), `*.sch` (Schematron-Regeln)
  - Quellen: https://www.xrechnung.org/

- **Factur-X/ZUGFeRD**: `agents/einvoice/facturx/resources/official/`
  - Erwartete Dateien: `*.xsd` (EN16931/Factur-X XSD)
  - Quellen: https://www.factur-x.eu/

### Validator-Modi

Die Validatoren unterstützen zwei Modi:

#### TEMP-Mode (Default)

- **ENV**: `EINVOICE_VALIDATION_MODE=temp` (oder nicht gesetzt)
- **Verhalten**: Stub-Validierung mit vereinfachten Regeln
- **Verwendung**: Erster Durchlauf, Entwicklung, Tests ohne offizielle Ressourcen
- **Limitation**: Keine echte Schema/Schematron-Validierung

#### OFFICIAL-Mode

- **ENV**: `EINVOICE_VALIDATION_MODE=official`
- **Verhalten**: Echte Validierung mit lxml XMLSchema/Schematron
- **Voraussetzung**: Offizielle XSD/Schematron-Dateien müssen in `resources/official/` vorhanden sein
- **Fallback**: Automatischer Fallback zu TEMP-Mode wenn Ressourcen fehlen

### Implementierung

- **XRechnung**: `agents/einvoice/xrechnung/validator.py`
  - Schema-Validierung: `lxml.etree.XMLSchema`
  - Schematron-Validierung: `lxml.isoschematron.Schematron`

- **Factur-X**: `agents/einvoice/facturx/validator.py`
  - Schema-Validierung: `lxml.etree.XMLSchema`
  - Kein Schematron (nur Schema)

## PDF/A-3 Best-Effort Implementierung

### Überblick

Die PDF/A-3-Erzeugung verwendet ReportLab für das Grundgerüst und pikepdf für PDF/A-3-Konformität.

**Wichtig**: PDF/A ist "Best-Effort" – formale Konformität wird erst später mit externem Validator/GOBD-Prozess abschließend belegt.

### Implementierung

- **Datei**: `agents/einvoice/facturx/generator.py`
- **Funktion**: `embed_xml_to_pdf()`

### Bestandteile

1. **ReportLab**: PDF-Grundgerüst mit einfacher Textseite
2. **XMP-Metadaten**: PDF/A-3-Konformitätsflags (`pdfaid:part=3`, `pdfaid:conformance=B`)
3. **ICC-Profil**: Via pikepdf-Normalisierung
4. **AF-Relationship**: ZUGFeRD/Factur-X Attachment (`/AF` Array im Root)
5. **Embedded File Specification**: XML als `/EmbeddedFile` mit `/AFRelationship=/Alternative`

### Interne Checks

Die Tests (`tests/einvoice/test_pdfa_best_effort.py`) prüfen:

- XMP-Metadaten (PDF/A-3 Schlüssel, Producer, CreationDate)
- AF-Relationship (ZUGFeRD/FX-Attachment)
- Embedded File Specification
- Determinismus (gleiche Inputs → gleiche Bytes)

### Externer Validator (Optional)

- **ENV**: `PDF_A_VALIDATOR_CMD` (z.B. `veraPDF --format pdfa-3`)
- **Verhalten**: Wenn gesetzt, wird genau **eine** erzeugte PDF an den externen Validator gepiped
- **Ergebnis**: Nur als Hinweis im Test (nicht failen)
- **Hinweis**: Nicht gesetzt im ersten Durchlauf

### Fallback

Falls ReportLab oder pikepdf nicht verfügbar sind, wird automatisch auf den TEMP-Stub zurückgefallen (`_embed_xml_to_pdf_stub()`).

## ENV-Gates

### Validator-Mode

- `EINVOICE_VALIDATION_MODE`: `temp` (Default) oder `official`

### Externer PDF/A-Validator

- `PDF_A_VALIDATOR_CMD`: Optionaler externer Validator-Befehl (nicht gesetzt im ersten Durchlauf)

## Trade-offs & Limitierungen

### Validatoren

- **TEMP-Mode**: Schnell, aber keine echte Schema-Validierung
- **OFFICIAL-Mode**: Echte Validierung, aber erfordert manuelle Ressourcen-Platzierung

### PDF/A-3 Best-Effort

- **Keine Garantie**: Formale Konformität wird erst mit externem Validator belegt
- **Interne Checks**: Mindestkonformität (XMP, AF, Embedded File)
- **Determinismus**: Best-Effort (pikepdf-Normalisierung kann kleine Unterschiede verursachen)

### Dependencies

- **reportlab**: Erforderlich für PDF-Grundgerüst
- **pikepdf**: Erforderlich für PDF/A-3-Konformität
- **lxml**: Erforderlich für OFFICIAL-Mode Validierung

## Bekannte Einschränkungen

1. **Ressourcen-Platzierung**: Offizielle XSD/Schematron müssen manuell abgelegt werden (kein Netz-Fetch)
2. **PDF/A-Konformität**: Best-Effort, keine formale Garantie ohne externen Validator
3. **Determinismus**: PDF-Bytes können durch pikepdf-Normalisierung kleine Unterschiede aufweisen

