<!-- 540266e9-f692-42dc-9bcb-b162a6e04688 4ec33e96-a4a6-49f4-8e37-5b32196987c5 -->
# E-Invoice Hardening & Operate (One-Shot) – 2025-10-30

## Übersicht

Hardening des E-Rechnung-Moduls durch:

1. Ersetzen der TEMP-Validatoren durch OFFICIAL-Mode mit echten XSD/Schematron-Ressourcen
2. PDF/A-3 Best-Effort Implementierung (ReportLab+pikepdf statt TEMP_PDF_A_WRITER)
3. Morning-Operate für E-Rechnung (analog Mahnwesen)
4. Konservative Dev-Deps-Anhebung
5. Dokumentation

## 1. Validator-Ressourcen & OFFICIAL-Mode

### 1.1 Ressourcen-Struktur anlegen

- **Dateien**: `agents/einvoice/xrechnung/resources/official/`, `agents/einvoice/facturx/resources/official/`
- **Aktion**: Ordnerstruktur erstellen, README.md mit Quellen-Hinweis für manuelle Platzierung der offiziellen XSD/Schematron-Dateien
- **Hinweis**: Offizielle Dateien müssen manuell abgelegt werden (kein Netz-Fetch in Tests)

### 1.2 Validator-Implementierung (XRechnung)

- **Datei**: `agents/einvoice/xrechnung/validator.py`
- **Änderungen**:
- ENV-Variable `EINVOICE_VALIDATION_MODE` (Default: `OFFICIAL`, Fallback: `TEMP`)
- OFFICIAL-Mode: `lxml.etree.XMLSchema` + `lxml.isoschematron.Schematron` für echte Validierung
- TEMP-Mode: bestehende Stub-Logik beibehalten
- Rückgabe: `schema_ok`, `schematron_ok`, `messages` (inkl. detaillierter Fehlermeldungen)

### 1.3 Validator-Implementierung (Factur-X)

- **Datei**: `agents/einvoice/facturx/validator.py`
- **Änderungen**: Analog XRechnung, jedoch nur Schema-Validierung (kein Schematron für Factur-X)

### 1.4 Tests aktualisieren

- **Dateien**: `tests/einvoice/test_xrechnung_pipeline.py`, `tests/einvoice/test_facturx_pipeline.py`
- **Änderungen**: Tests verwenden OFFICIAL-Mode (Default), prüfen `schema_ok=true`, `schematron_ok=true` für 10 Belege

## 2. PDF/A-3 Best-Effort Implementierung

### 2.1 Generator erweitern

- **Datei**: `agents/einvoice/facturx/generator.py`
- **Änderungen**:
- Funktion `embed_xml_to_pdf()` ersetzt durch ReportLab+pikepdf-Pfad
- ReportLab: PDF-Grundgerüst mit XMP-Metadaten (PDF/A-3 konform)
- pikepdf: Nachbearbeitung (ICC-Profil, AF-Relationship, Embedded File Specification)
- Determinismus: Fixe Producer-Strings, sortierte Dicts, injizierbares `now()`
- ENV-Gate: `PDF_A_VALIDATOR_CMD` für optionalen externen Validator

### 2.2 PDF/A-3 Tests

- **Datei**: `tests/einvoice/test_pdfa_best_effort.py` (NEU)
- **Inhalt**:
- XMP-Metadaten-Prüfung (PDF/A-3 Schlüssel, Producer, CreationDate)
- AF-Relationship-Prüfung (ZUGFeRD/FX-Attachment)
- Embedded File Specification prüfen
- Determinismus-Test (gleiche Inputs → gleiche Bytes)
- Optional: externer Validator via ENV (nur Hinweis, kein Fail)

## 3. Morning-Operate für E-Rechnung

### 3.1 KPI-Engine

- **Datei**: `tools/operate/einvoice_kpi.py` (NEU)
- **Funktionen**:
- `EInvoiceKpiAggregator`: Aggregiert Kennzahlen aus Artefakten (`artifacts/reports/einvoice/<tenant>/`)
- KPIs: `count_ok`, `schema_fail`, `schematron_fail`, `pdfa_checks_ok`, `duration_ms`
- PII-Redaction in Logs/MD
- JSON/MD-Output analog `tools/operate/kpi_engine.py`

### 3.2 Morning-Operate Orchestrator

- **Datei**: `tools/operate/einvoice_morning.py` (NEU)
- **Funktionen**:
- CLI: `--tenant`, `--dry-run`, `--count` (für Generate-Limit)
- Orchestriert: Generate (mit Limit), KPI-Aggregation, optional Approve-Subset, Summary-MD
- Summary: `artifacts/reports/einvoice/<tenant>/<YYYY-MM-DD>_summary.md`
- PII-Redaction, deterministische Zeiten (UTC)

### 3.3 VS Code Tasks

- **Datei**: `.vscode/tasks.json`
- **Änderungen**: Zwei neue Tasks hinzufügen:
- "E-Invoice: Morning Operate (Dry-Run)" mit `.env`-Sourcing
- "E-Invoice: Morning Operate (Live)" mit `.env`-Sourcing

### 3.4 Tests

- **Datei**: `tests/einvoice/test_einvoice_morning_operate.py` (NEU)
- **Inhalt**:
- Dry-Run erzeugt Summary
- Kennzahlen plausibel (count_ok > 0 wenn erfolgreich)
- Keine PII in Summary
- Deterministische Zeiten (UTC)

## 4. Dev-Deps konservativ anheben

### 4.1 Requirements aktualisieren

- **Datei**: `requirements-dev.txt`
- **Änderungen**: Minimal konservative Versionsanhebung für:
- `pytest`, `pytest-cov`, `httpx`, `freezegun`, `requests`, `pyyaml`, `lxml`, `jinja2`
- Optional: `pikepdf`, `reportlab` (falls nicht in Runtime-Deps)
- **Note**: Keine Major-Sprünge, Tests bleiben offline grün

## 5. Dokumentation

### 5.1 Hardening-Doku

- **Datei**: `docs/einvoice/hardening.md` (NEU)
- **Inhalt**:
- Ressourcenquellen (Dateipfade, offizielle Quellen für XSD/Schematron)
- Validator-Modi (OFFICIAL vs TEMP, ENV-Switch)
- PDF/A-Best-Effort Limitierungen, interne Checks, ENV-Gates
- Trade-offs, bekannte Einschränkungen

### 5.2 Morning-Runbook

- **Datei**: `docs/agents/einvoice_morning_runbook.md` (NEU)
- **Inhalt**: Analog `docs/agents/morning_operate_runbook.md`
- Ablauf, Flags (`--tenant`, `--dry-run`, `--count`)
- Artefakte (`artifacts/reports/einvoice/<tenant>/`)
- Typische Fehler, Troubleshooting

## 6. CI-Verifikation

- **Datei**: `.github/workflows/python.yml`
- **Status**: Bereits vorhanden, deckt `tests/einvoice/**` ab
- **Aktion**: Keine Änderungen nötig

## Constraints & Guards

- Keine Netz-Fetches in Tests (alle Ressourcen lokal)
- Multi-Tenant strikt (tenant_id → DTO → Artefaktpfad)
- Determinismus: TZ=UTC, PYTHONHASHSEED=0, injizierbares `now()`
- PII-Redaction in Logs/MD
- Keine Commits/Pushes in diesem Block
- Nur Pfade aus ALLOWED_CODE_PATHS ändern
- **Validatoren**: Default `EINVOICE_VALIDATION_MODE=temp` für ersten Durchlauf; OFFICIAL nur wenn Ressourcen vorhanden
- **PDF/A**: Best-Effort (kein externer Validator erforderlich für Tests); `PDF_A_VALIDATOR_CMD` nicht gesetzt im ersten Durchlauf

## Testing-Strategie

- Fokustests: `tests/einvoice/test_*pipeline.py`, `test_pdfa_best_effort.py`, `test_einvoice_morning_operate.py`
- Umgebung: `TZ=UTC PYTHONHASHSEED=0 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
- Optional: Externer PDF/A-Validator via ENV `PDF_A_VALIDATOR_CMD` (Smoke mit 1 Datei, sonst skip)

### To-dos

- [ ] Ressourcen-Struktur anlegen: agents/einvoice/xrechnung/resources/official/ und agents/einvoice/facturx/resources/official/ mit README.md (Quellen-Hinweis für manuelle Platzierung)
- [ ] agents/einvoice/xrechnung/validator.py: OFFICIAL-Mode mit lxml XMLSchema+Schematron implementieren, TEMP-Mode via ENV beibehalten
- [ ] agents/einvoice/facturx/validator.py: OFFICIAL-Mode mit lxml XMLSchema implementieren, TEMP-Mode via ENV beibehalten
- [ ] Tests aktualisieren: test_xrechnung_pipeline.py und test_facturx_pipeline.py auf OFFICIAL-Mode umstellen (Default)
- [ ] agents/einvoice/facturx/generator.py: embed_xml_to_pdf() durch ReportLab+pikepdf-Pfad ersetzen (XMP, ICC, AF, Embedded File)
- [ ] tests/einvoice/test_pdfa_best_effort.py erstellen: XMP-Prüfung, AF-Relationship, Embedded File, Determinismus, optional externer Validator
- [ ] tools/operate/einvoice_kpi.py erstellen: KPI-Aggregation (count_ok, schema_fail, schematron_fail, pdfa_checks_ok, duration_ms) mit PII-Redaction
- [ ] tools/operate/einvoice_morning.py erstellen: Orchestrator (Generate, KPI, optional Approve, Summary-MD) mit CLI-Flags
- [ ] .vscode/tasks.json: Zwei Tasks für E-Invoice Morning Operate (Dry-Run/Live) hinzufügen
- [ ] tests/einvoice/test_einvoice_morning_operate.py erstellen: Dry-Run-Test, KPI-Plausibilität, PII-Redaction, Determinismus
- [ ] requirements-dev.txt: Konservative Versionsanhebung für pytest/httpx/freezegun/requests/pyyaml/lxml/jinja2 (optional: pikepdf/reportlab)
- [ ] docs/einvoice/hardening.md erstellen: Ressourcenquellen, Validator-Modi, PDF/A-Limitierungen, ENV-Gates, Trade-offs
- [ ] docs/agents/einvoice_morning_runbook.md erstellen: Ablauf, Flags, Artefakte, Troubleshooting