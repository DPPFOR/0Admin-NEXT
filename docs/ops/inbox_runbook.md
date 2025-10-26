# Inbox Runbook

## Übersicht

Dieses Runbook beschreibt die Betriebsabläufe für die idempotente, mandantenfähige Inbox-Schicht von 0Admin-NEXT.

## Start/Stop

### Start
```bash
# 1. Virtuelles Environment aktivieren
source .venv/bin/activate

# 2. Dependencies installieren
pip install -r requirements.txt

# 3. Datenbank migrieren
TZ=UTC PYTHONHASHSEED=0 alembic -c alembic.ini upgrade head

# 4. Smoke-Tests ausführen
TZ=UTC PYTHONHASHSEED=0 python -m pytest -q tests/inbox -k 'smoke or idempotent or views or audit or logger'
```

### Stop
```bash
# Keine speziellen Stop-Prozeduren erforderlich
# Die Inbox-Schicht läuft als stateless Service
```

## Migrate

### Datenbank-Migration
```bash
# Migration ausführen
TZ=UTC PYTHONHASHSEED=0 alembic -c alembic.ini upgrade head

# Migration-Status prüfen
alembic -c alembic.ini current

# Migration rückgängig machen (falls nötig)
alembic -c alembic.ini downgrade -1
```

### Schema-Validierung
```bash
# Views prüfen
python -c "
import os
from sqlalchemy import create_engine, text
e = create_engine(os.environ['DATABASE_URL'], future=True)
with e.begin() as c:
    v1 = c.execute(text('SELECT COUNT(*) FROM inbox_parsed.v_inbox_by_tenant')).scalar()
    v2 = c.execute(text('SELECT COUNT(*) FROM inbox_parsed.v_invoices_latest')).scalar()
    print(f'v_inbox_by_tenant: {v1} rows')
    print(f'v_invoices_latest: {v2} rows')
"
```

## Smoke-Tests

### Vollständige Smoke-Suite
```bash
# Alle Inbox-Tests
TZ=UTC PYTHONHASHSEED=0 python -m pytest -q tests/inbox -k 'smoke or idempotent or views or audit or logger'
```

### Einzelne Test-Kategorien
```bash
# Idempotenz-Tests
python -m pytest -q tests/inbox/test_idempotent_import.py

# Views-Contract-Tests
python -m pytest -q tests/inbox/test_views_contract.py

# Audit-Log-Tests
python -m pytest -q tests/inbox/test_audit_log.py

# PII-Redaction-Tests
python -m pytest -q tests/inbox/test_logger_pii.py
```

## Typische Fehler

### FK-Fehler
**Symptom:** `FOREIGN KEY constraint failed`
**Ursache:** Referenzierte Tabelle existiert nicht oder FK-Constraint fehlt
**Lösung:**
```bash
# Schema prüfen
psql $DATABASE_URL -c "\d inbox_parsed.parsed_item_chunks"

# FK-Constraint prüfen
psql $DATABASE_URL -c "
SELECT conname, contype 
FROM pg_constraint 
WHERE conrelid = 'inbox_parsed.parsed_item_chunks'::regclass
"
```

### UNIQUE-Constraint-Fehler
**Symptom:** `UNIQUE constraint failed`
**Ursache:** Duplikate in UNIQUE-Constraints
**Lösung:**
```bash
# Duplikate finden
psql $DATABASE_URL -c "
SELECT tenant_id, content_hash, COUNT(*) 
FROM inbox_parsed.parsed_items 
GROUP BY tenant_id, content_hash 
HAVING COUNT(*) > 1
"

# Duplikate bereinigen (VORSICHT!)
psql $DATABASE_URL -c "
DELETE FROM inbox_parsed.parsed_items 
WHERE id NOT IN (
    SELECT MIN(id) 
    FROM inbox_parsed.parsed_items 
    GROUP BY tenant_id, content_hash
)
"
```

### Trigger-Fehler
**Symptom:** `function update_updated_at_column() does not exist`
**Ursache:** Trigger-Funktion fehlt
**Lösung:**
```bash
# Trigger-Funktion manuell erstellen
psql $DATABASE_URL -c "
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS \$\$
BEGIN
    NEW.updated_at = timezone('utc', now());
    RETURN NEW;
END;
\$\$ language 'plpgsql';
"
```

## Recovery

### Views neu aufbauen
```bash
# Views löschen und neu erstellen
psql $DATABASE_URL -c "
DROP VIEW IF EXISTS inbox_parsed.v_invoices_latest;
DROP VIEW IF EXISTS inbox_parsed.v_inbox_by_tenant;
"

# Views neu erstellen
psql $DATABASE_URL -c "
CREATE VIEW inbox_parsed.v_inbox_by_tenant AS
SELECT 
    tenant_id,
    COUNT(*) as total_items,
    COUNT(CASE WHEN doctype = 'invoice' THEN 1 END) as invoices,
    COUNT(CASE WHEN doctype = 'payment' THEN 1 END) as payments,
    COUNT(CASE WHEN doctype = 'other' THEN 1 END) as others,
    AVG(confidence) as avg_confidence
FROM inbox_parsed.parsed_items
GROUP BY tenant_id;

CREATE VIEW inbox_parsed.v_invoices_latest AS
SELECT * FROM inbox_parsed.parsed_items 
WHERE doctype = 'invoice'
ORDER BY created_at DESC;
"
```

### Schema-Reparatur
```bash
# Vollständige Migration neu ausführen
alembic -c alembic.ini downgrade base
alembic -c alembic.ini upgrade head
```

## Log-PII-Hinweis

### PII-Redaction aktiviert
Die Logger-Konfiguration redactiert automatisch:
- **IBAN:** `DE89370400440532013000` → `DE**...****`
- **E-Mail:** `john.doe@example.com` → `j***@example.com`
- **Telefon:** `+49 30 12345678` → `+4***...`

### PII-Redaction testen
```bash
# PII-Redaction testen
python -c "
from backend.core.observability.logging import JSONFormatter
import logging
formatter = JSONFormatter()
record = logging.LogRecord('test', 20, '', 0, 'IBAN: DE89370400440532013000', (), None)
print(formatter.format(record))
"
```

## Monitoring

### Datenbank-Status
```bash
# Tabellen-Größen
psql $DATABASE_URL -c "
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname IN ('inbox_parsed', 'ops')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Audit-Log-Status
psql $DATABASE_URL -c "
SELECT 
    op,
    COUNT(*) as count,
    MIN(ts) as earliest,
    MAX(ts) as latest
FROM ops.audit_log 
GROUP BY op
ORDER BY count DESC;
"
```

### Performance-Metriken
```bash
# Views-Performance
psql $DATABASE_URL -c "
EXPLAIN ANALYZE SELECT * FROM inbox_parsed.v_inbox_by_tenant;
EXPLAIN ANALYZE SELECT * FROM inbox_parsed.v_invoices_latest LIMIT 10;
"
```

## Troubleshooting

### Häufige Probleme

1. **Migration schlägt fehl**
   - Prüfe DATABASE_URL
   - Prüfe Berechtigungen
   - Prüfe Schema-Existenz

2. **Tests schlagen fehl**
   - Prüfe DATABASE_URL
   - Prüfe TZ=UTC und PYTHONHASHSEED=0
   - Prüfe Dependencies

3. **PII-Redaction funktioniert nicht**
   - Prüfe Logger-Konfiguration
   - Prüfe JSONFormatter-Import
   - Teste manuell

### Debug-Commands
```bash
# Datenbank-Verbindung testen
python -c "
import os
from sqlalchemy import create_engine
e = create_engine(os.environ['DATABASE_URL'], future=True)
with e.begin() as conn:
    result = conn.execute('SELECT 1').scalar()
    print(f'DB connection OK: {result}')
"

# Schema-Existenz prüfen
psql $DATABASE_URL -c "
SELECT schema_name FROM information_schema.schemata 
WHERE schema_name IN ('inbox_parsed', 'ops');
"
```

## Kontakt

Bei Problemen oder Fragen:
- **Logs:** JSON-formatierte Logs mit trace_id und tenant_id
- **Audit:** Alle Operationen werden in ops.audit_log protokolliert
- **PII:** Automatische Redaction in allen Logs aktiviert
