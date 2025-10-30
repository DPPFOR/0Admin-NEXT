# Morning Operate Runbook — E-Invoice

## Zweck

Täglicher Einlauf (empfohlen 07:30 CET) zur Bewertung der E-Rechnung-Generierung: Generate (mit Limit), KPI-Aggregation, optional Approve-Subset, Summary-MD mit PII-Redaction.

## Ablauf (pro Tenant)

1. **Generate** (`tools/operate/einvoice_morning.py`)
   - Generiert E-Invoices bis zum konfigurierten Limit (Default: 10)
   - Format: Factur-X oder XRechnung (via `--format`)
   - Speichert Artefakte unter `artifacts/einvoice/<tenant>/`

2. **KPI-Aggregation** (`tools/operate/einvoice_kpi.py`)
   - Aggregiert Kennzahlen aus Artefakten
   - KPIs: `count_ok`, `schema_fail`, `schematron_fail`, `pdfa_checks_ok`, `duration_ms`
   - Erstellt `YYYY-MM-DD.json` & `.md`

3. **Summary** (`YYYY-MM-DD_summary.md`)
   - Enthält Generate-Info, KPI-Werte, PII-redacted

## Werkzeuge

- Orchestrator: `python tools/operate/einvoice_morning.py --tenant <id>`
- Alle Tenants: `--all-tenants`
- Dry-Run: `--dry-run` (keine Writes, Summary wird dennoch geschrieben)
- Format: `--format facturx` oder `--format xrechnung` (Default: `facturx`)
- Count: `--count <n>` (Default: 10)
- VS Code Tasks:
  - „E-Invoice: Morning Operate (Dry-Run)"
  - „E-Invoice: Morning Operate (Live)"

## Flags

- `--tenant <uuid>`: Spezifischer Tenant
- `--all-tenants`: Alle Tenants verarbeiten
- `--date YYYY-MM-DD`: Report-Datum (Default: heute)
- `--dry-run`: Skip writes, generiere Summary
- `--count <n>`: Max Invoices zu generieren (Default: 10)
- `--format <facturx|xrechnung>`: Invoice-Format (Default: facturx)

## Artefakte

- Generate: `artifacts/einvoice/<tenant>/<invoice_no>/`
- KPI: `artifacts/reports/einvoice/<tenant>/<YYYY-MM-DD>.json|.md`
- Summary: `artifacts/reports/einvoice/<tenant>/<YYYY-MM-DD>_summary.md`

## KPI-Felder

| Feld | Beschreibung |
| --- | --- |
| `count_total` | Anzahl generierter Invoices |
| `count_ok` | Anzahl erfolgreich validierter Invoices (`schema_ok=true`, `schematron_ok=true`) |
| `schema_fail` | Anzahl Schema-Validierungsfehler |
| `schematron_fail` | Anzahl Schematron-Validierungsfehler |
| `pdfa_checks_ok` | Anzahl PDF/A-Checks OK (`has_xmp`, `has_af`, `has_embedded`) |
| `pdfa_checks_total` | Anzahl PDF/A-Checks durchgeführt |
| `duration_ms` | Gesamtdauer (ms) |
| `duration_avg_ms` | Durchschnittsdauer (ms) |

## PII-Redaction

- E-Mail-Adressen: `<EMAIL>`
- IBAN: `<IBAN>`
- VAT-IDs: `<VAT_ID>`
- Automatisch in Logs/MD angewendet

## Troubleshooting

- **Keine Invoices generiert**: Prüfe `--count` und verfügbare Scenarios (`iter_sample_scenarios()`)
- **Schema-Failures**: Prüfe `validation.json` in Invoice-Verzeichnissen; ggf. `EINVOICE_VALIDATION_MODE=temp` setzen
- **PDF/A-Checks fail**: Prüfe ob `reportlab` und `pikepdf` installiert sind (`requirements-dev.txt`)
- **KPI-Report leer**: Prüfe ob Artefakte unter `artifacts/einvoice/<tenant>/` vorhanden sind

## Beispiel-Ausführung

```bash
# Dry-Run für einen Tenant
python tools/operate/einvoice_morning.py --tenant 00000000-0000-0000-0000-000000000001 --dry-run --count 5

# Live für alle Tenants
python tools/operate/einvoice_morning.py --all-tenants --count 10 --format facturx

# Mit spezifischem Datum
python tools/operate/einvoice_morning.py --tenant <uuid> --date 2025-01-01
```

## Go-Live Checkliste (Morning)

- ✅ KPI Summary ohne kritische Warnungen
- ✅ `count_ok` > 0 (mindestens einige erfolgreiche Validierungen)
- ✅ `schema_fail` und `schematron_fail` im tolerierbaren Bereich
- ✅ PDF/A-Checks OK für Factur-X-Invoices
- ✅ Summary ohne PII-Lecks

## Hinweise

- **Determinismus**: `TZ=UTC`, `PYTHONHASHSEED=0` für reproduzierbare Ergebnisse
- **Retention**: KPI-Reports & Summaries ≥ 90 Tage aufbewahren
- **Redaction-Probe**: Regelmäßig `tools/operate/redaction_probe.py` laufen lassen
- **Dry-Run**: Generiert Summary, aber keine Artefakte (nur Simulation)

