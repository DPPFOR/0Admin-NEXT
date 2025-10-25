# Mahnwesen Betriebsleitfaden

## Start/Stop

### VS Code Tasks (Empfohlen)
- `Ctrl+Shift+P` → "Tasks: Run Task" → "Mahnwesen: Dry-Run (Go-Live)"
- `Ctrl+Shift+P` → "Tasks: Run Task" → "Mahnwesen: DB-Smoke (Flock, RLS-ON)"

### CLI-Kommandos
```bash
# Dry-Run für Tenant
python tools/flock/playbook_mahnwesen.py --tenant <UUID> --dry-run --limit 50

# Dashboard anzeigen
python tools/flock/mahnwesen_console.py --tenant <UUID>

# Tagesreport generieren
python tools/flock/mahnwesen_daily_report.py --tenant <UUID>
```

## Tägliche Checks

### 1. Dashboard prüfen
```bash
python tools/flock/mahnwesen_console.py --tenant <UUID>
```
- ✅ Status: "success" oder "0-Fälle"
- ⚠️ Warnings: Prüfen und ggf. beheben
- ❌ Errors: Sofort prüfen

### 2. Dry-Run durchführen
```bash
python tools/flock/playbook_mahnwesen.py --tenant <UUID> --dry-run --verbose
```
- Prüfe: Anzahl überfälliger Rechnungen
- Prüfe: Verteilung auf Mahnstufen (1/2/3)
- Prüfe: Geplante Notices (keine Outbox-Writes im Dry-Run)

### 3. Reports generieren
```bash
python tools/flock/mahnwesen_daily_report.py --tenant <UUID>
```
- CSV/JSON Reports unter `artifacts/reports/mahnwesen/<tenant>/`
- Aggregierte Daten pro Mahnstufe
- Summe Beträge und Anzahl Kunden

## Typische Fehlerbilder & Behebung

### ❌ "No dry-run report found"
**Ursache:** Kein Dry-Run für heute durchgeführt
**Behebung:** 
```bash
python tools/flock/playbook_mahnwesen.py --tenant <UUID> --dry-run
```

### ❌ "Error fetching overdue invoices"
**Ursache:** Read-API nicht erreichbar
**Behebung:**
1. Prüfe API-Status: `curl http://localhost:8000/healthz`
2. Starte API: `uvicorn backend.app:app --reload`
3. Prüfe Tenant-Isolation: `X-Tenant-Id` Header

### ❌ "Rechnung X steht auf der Sperrliste"
**Ursache:** Rechnung in Stop-List konfiguriert
**Behebung:** Stop-List in `agents/mahnwesen/config.py` prüfen/anpassen

### ❌ "Rechnungsbetrag unter Mindestbetrag"
**Ursache:** `min_amount_cents` zu hoch konfiguriert
**Behebung:** Mindestbetrag in Config anpassen

### ⚠️ "Letzte Mahnung zu recent"
**Ursache:** Spam-Schutz aktiv (min. 1 Tag zwischen Mahnungen)
**Behebung:** Warten oder Spam-Schutz in Policies anpassen

## Freigabe-Flow für Vorlagen

### 1. Template-Änderungen testen
```bash
# Test Template-Rendering
python -m pytest tests/agents_mahnwesen/test_compose_template_offline.py -v
```

### 2. Dry-Run mit neuen Templates
```bash
python tools/flock/playbook_mahnwesen.py --tenant <UUID> --dry-run --verbose
```

### 3. Template-Validierung
- Prüfe: Alle Pflichtfelder vorhanden (Mandant, Kunde, Rechnung, Betrag, Stufe)
- Prüfe: Deutsche Texte korrekt
- Prüfe: Beträge formatiert (2 Dezimalstellen)
- Prüfe: Datum-Format (DD.MM.YYYY)

### 4. Freigabe
- Templates in `agents/mahnwesen/templates/` committen
- VS Code Task ausführen
- Dashboard prüfen

## Ansprechpartner/Fallback

### Technische Probleme
- **Read-API Down:** `uvicorn backend.app:app --reload`
- **DB-Verbindung:** `DATABASE_URL` prüfen
- **Flock-Fehler:** Logs in `artifacts/reports/mahnwesen/`

### Konfiguration
- **Mindestbetrag:** `agents/mahnwesen/config.py` → `min_amount_cents`
- **Schonfrist:** `agents/mahnwesen/config.py` → `grace_days`
- **Stop-List:** `agents/mahnwesen/config.py` → `stop_listed_invoices`

### Monitoring
- **Logs:** `artifacts/reports/mahnwesen/<tenant>/`
- **CSV-Reports:** Tägliche Aggregate
- **JSON-Reports:** Vollständige Daten

### Notfall-Eskalation
1. **Sofort:** Dashboard prüfen → Status "error"?
2. **5 Min:** Dry-Run durchführen → Fehler reproduzieren
3. **15 Min:** Logs analysieren → `artifacts/reports/mahnwesen/`
4. **30 Min:** Konfiguration prüfen → `agents/mahnwesen/config.py`
5. **1h:** Fallback auf manuelle Mahnungen

## Wartung

### Wöchentlich
- CSV-Reports archivieren
- Logs aufräumen (älter als 30 Tage)
- Template-Versionen prüfen

### Monatlich
- Stop-List aktualisieren
- Mindestbeträge anpassen
- Performance-Metriken auswerten

### Bei Updates
- Alle Tests: `pytest tests/agents_mahnwesen/`
- Dry-Run für alle Tenants
- Dashboard-Funktionalität prüfen

# Schema-Kompatibilität (Importer ↔ Chunks) – 2025-02-16
Betroffene Tabelle: inbox_parsed.parsed_item_chunks.
Problem: Legacy-Spalte item_id NOT NULL kollidiert mit Importer, der parsed_item_id schreibt.
Lösung:

ALTER TABLE … DROP COLUMN IF EXISTS item_id CASCADE;

ALTER TABLE … ADD COLUMN item_id UUID GENERATED ALWAYS AS (parsed_item_id) STORED;
Begründung: Backwards-Kompatibilität für bestehende Views/Queries, kein Code-Change im Importer.
Prüfung: SELECT count(*) FROM inbox_parsed.parsed_items; und …parsed_item_chunks; > 0 nach Import.
Rückbau: nicht erforderlich