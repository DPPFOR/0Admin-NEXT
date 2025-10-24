# Read-API Troubleshooting Guide

## Symptom: HTTP 422 "Field required" für X-Tenant-ID Header

### Problem
FastAPI erkennt den `X-Tenant-ID` Header nicht und gibt HTTP 422 zurück.

### Ursache
FastAPI konvertiert standardmäßig Header-Namen mit `convert_underscores=True`, wodurch `X-Tenant-ID` zu `x-tenant-id` wird.

### Lösung
```python
# Korrekt:
def require_tenant(tenant: str = Header(..., alias="X-Tenant-ID", convert_underscores=False)) -> str:

# Falsch:
def require_tenant(tenant: str = Header(..., alias="X-Tenant-ID")) -> str:
```

### Test
```bash
curl -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  'http://127.0.0.1:8000/inbox/read/summary?limit=1'
# Erwartet: HTTP 200, nicht HTTP 422
```

---

## Symptom: HTTP 500 "Internal Server Error" nach Header-Fix

### Problem
Header wird erkannt, aber API gibt HTTP 500 zurück.

### Ursache
Datenbankschema-Mismatch: Code erwartet andere Spaltennamen als in der View vorhanden.

### Diagnose
```bash
# Prüfe View-Spalten:
python -c "
import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:5434/zeroadmin')
cur = conn.cursor()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_schema = 'inbox_parsed' AND table_name = 'v_inbox_by_tenant' ORDER BY column_name;\")
print([col[0] for col in cur.fetchall()])
"
```

### Lösung
SQL-Query in `backend/apps/inbox/read_model/query.py` anpassen:

```python
# Vorher (falsch):
SELECT tenant_id, cnt_items, cnt_invoices, cnt_payments, cnt_other, ...

# Nachher (korrekt):
SELECT tenant_id, total_items, invoices, payments, others, ...
```

### Mapping-Tabelle
| Code erwartet | View hat | Lösung |
|----------------|----------|---------|
| `cnt_items` | `total_items` | `total_items` |
| `cnt_invoices` | `invoices` | `invoices` |
| `cnt_payments` | `payments` | `payments` |
| `cnt_other` | `others` | `others` |

---

## Symptom: DATABASE_URL Connection Error

### Problem
```
psycopg2.errors.InvalidDSN: invalid dsn: missing "=" after "postgresql+psycopg2://..."
```

### Ursache
Falsches URL-Format für psycopg2.

### Lösung
```bash
# Falsch:
DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5434/zeroadmin

# Korrekt:
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5434/zeroadmin
```

---

## Importer-Fehler: Reihenfolge der Datenbank-Operationen

### Korrekte Reihenfolge
1. **Tabellen** erstellen
2. **Spalten** definieren
3. **Unique Index** erstellen
4. **Foreign Keys** hinzufügen
5. **(Optional)** Trigger/Defaults

### Beispiel
```sql
-- 1. Tabelle
CREATE TABLE inbox_parsed.parsed_items (...);

-- 2. Spalten (bereits in CREATE TABLE)
-- 3. Unique Index
CREATE UNIQUE INDEX idx_parsed_items_tenant_id ON inbox_parsed.parsed_items(tenant_id);

-- 4. Foreign Keys
ALTER TABLE inbox_parsed.parsed_item_chunks 
ADD CONSTRAINT fk_chunks_item_id 
FOREIGN KEY (item_id) REFERENCES inbox_parsed.parsed_items(id);

-- 5. Trigger/Defaults (optional)
```

---

## Quick-Check Commands

### Header-Test
```bash
for H in "X-Tenant-ID" "X-Tenant-Id" "x-tenant-id"; do
  echo "=== $H ==="
  curl -sS -w '\nHTTP:%{http_code}\n' -H "$H: 00000000-0000-0000-0000-000000000001" \
    'http://127.0.0.1:8000/inbox/read/summary?limit=1'
done
```

### DB-Connection-Test
```bash
python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    print('✅ Database connection: OK')
    conn.close()
except Exception as e:
    print(f'❌ Database connection: FAIL - {e}')
"
```

### View-Schema-Check
```bash
python -c "
import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:5434/zeroadmin')
cur = conn.cursor()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_schema = 'inbox_parsed' AND table_name = 'v_inbox_by_tenant' ORDER BY column_name;\")
print('View columns:', [col[0] for col in cur.fetchall()])
"
```

---

## Troubleshooting-Flow

1. **HTTP 422** → Header-Problem → `convert_underscores=False`
2. **HTTP 500** → DB-Problem → Schema-Mapping prüfen
3. **Connection Error** → DATABASE_URL-Format prüfen
4. **Import Error** → Reihenfolge der DB-Operationen prüfen

---

*Letzte Aktualisierung: 2025-10-24*
*Erstellt nach: Read-API Header-Fix Session*
