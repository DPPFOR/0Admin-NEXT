# Inbox Read Model (Agent/Flock)

Dieses Read-Model stellt stabile Views für Agenten- und Tool-Zugriffe (z. B. Flock „whiteduck“) bereit. Es basiert ausschließlich auf den Tabellen `inbox_parsed.parsed_items` und `parsed_item_chunks` und bleibt schreibgeschützt.

## PostgreSQL-Views

Migration `20251020_read_model_views` erzeugt folgende Views im Schema `inbox_parsed`:

### `v_invoices_latest`
- Liefert je `(tenant_id, content_hash)` nur die jüngste Zeile mit `doc_type='invoice'`.
- Spalten: `id, tenant_id, content_hash, doc_type, quality_status, confidence, amount, invoice_no, due_date, created_at`.
- Implementierung: `ROW_NUMBER() OVER (PARTITION BY tenant_id, content_hash ORDER BY updated_at DESC) = 1`.

### `v_items_needing_review`
- Enthält alle Items mit `quality_status IN ('needs_review','rejected')`.
- Spalten: `id, tenant_id, doc_type, quality_status, confidence, created_at, content_hash`.

### `v_inbox_by_tenant`
- Aggregationssicht pro Tenant.
- Spalten: `tenant_id, cnt_items, cnt_invoices, cnt_needing_review, avg_confidence`.

Alle Views sind reguläre Views (`CREATE OR REPLACE VIEW`), damit sie migrationsunabhängig und offline aktualisiert werden können. Die Migration legt außerdem Indizes auf `tenant_id/doc_type`, `quality_status` sowie `updated_at` an, damit Flock-Anfragen auf großen Datenmengen performant bleiben.

## Typische SQL-Queries

```sql
SET search_path = inbox_parsed, public;

-- Neueste Rechnungen eines Tenants
SELECT *
FROM inbox_parsed.v_invoices_latest
WHERE tenant_id = :tenant
ORDER BY created_at DESC
LIMIT 20;

-- Offene Qualitätsprüfungen
SELECT *
FROM inbox_parsed.v_items_needing_review
WHERE tenant_id = :tenant;

-- Zusammenfassung
SELECT *
FROM inbox_parsed.v_inbox_by_tenant
WHERE tenant_id = :tenant;
```

> **Performance**: Die zusätzlichen Indizes stellen sicher, dass Filter auf `tenant_id`, `doc_type`, `quality_status` sowie Sortierungen nach `updated_at` Index-Support erhalten. `avg_confidence` wird aggregiert aus bereits gepflegten Confidence-Werten (NUMERIC(5,2)).

## Konsumations-Varianten für Flock (whiteduck)

### Variante A (empfohlen): CLI-Tool
1. Tool-Adapter in Flock registrieren, der `python tools/flows/query_read_model.py --tenant {tenant} --what {invoices|review|summary} --limit {k} --json` aufruft.
2. Ausgabe ist ein JSON-Array bzw. -Objekt ohne PII, direkt promptfähig.
3. Kein direkter DB-Zugriff notwendig (Least Privilege).

### Variante B: Direkter DB-Lesezugriff
- Read-only Credentials mit `search_path = inbox_parsed, public`.
- Rechte: ausschließlich `SELECT` auf den Views; kein DDL/DML.
- Statement-Timeout setzen (z. B. 5 s) und `tenant_id` immer parametrisiert binden.

Beispiel:

```sql
SET ROLE read_only_flock;
SET search_path = inbox_parsed, public;

SELECT * FROM v_invoices_latest WHERE tenant_id = :tenant ORDER BY created_at DESC LIMIT 20;
SELECT * FROM v_items_needing_review WHERE tenant_id = :tenant;
SELECT * FROM v_inbox_by_tenant WHERE tenant_id = :tenant;
```

## Sicherheit & Guardrails
- Keine Ausgabe der Roh-Payloads; Views enthalten nur aggregierte bzw. notwendige Felder.
- Read-only User (oder CLI) reichen aus; kein Schreibrecht erforderlich.
- Row-Level Filter erfolgt anhand der `tenant_id`-Filter in Views/Queries – Flock muss diesen Parameter liefern.

## Weiterführende Ressourcen
- DTOs & Query-Helpers: `backend/apps/inbox/read_model/`
- CLI: `tools/flows/query_read_model.py`
- Tests: `tests/inbox/test_read_model_shape.py`, `tests/inbox/test_read_model_db.py`
