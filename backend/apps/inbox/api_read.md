# Read API v1 — Inbox & Parsed

Endpoints
- GET `/api/v1/inbox/items` — Keyset paging (HMAC cursor), tenant scoped
- GET `/api/v1/inbox/items/{id}` — Single item
- GET `/api/v1/parsed/items` — Keyset paging, tenant scoped
- GET `/api/v1/parsed/items/{id}` — Single parsed

Headers
- `X-Tenant: <uuid>` (required)

Security & Policy
- `READ_MAX_LIMIT` caps `limit` (default 100).
- Cursor is an HMAC-signed payload `{created_at, id}` using `CURSOR_HMAC_KEY`.
- No PII/Blobs: responses exclude raw URIs and filenames; parsed payload is whitelisted (`doc_type, invoice_no, amount, due_date`).

Observability
- Logs: `trace_id`, `tenant_id`, `actor_role=user`, `endpoint`, `duration_ms`, `result_count`.
- Metrics: `inbox_read_total`, `parsed_read_total`, `read_duration_ms` histogram.

## Cursor
- Opaque, HMAC-signiert mit `CURSOR_HMAC_KEY`; nicht interpretierbar oder clientseitig konstruierbar.
- Manipulierter/ungültiger Cursor führt zu `400 invalid_cursor`.
- Stabilität: Cursor bleibt gültig, bis Datenänderungen die Menge vor dem Cursor beeinflussen (typische Keyset-Semantik; keine globale Konsistenzgarantie).

Beispiel
- Request (erste Seite): `GET /api/v1/inbox/items?limit=50` mit Header `X-Tenant: <uuid>`
- Response:
  ```json
  {
    "items": [ {"id": "...", "status": "validated", "tenant_id": "...", ...} ],
    "next": "eyJjcmVhdGVkX2F0IjoiMjAyNS0xMC0xOFQxMDozMDowMFoiLCJpZCI6Ij...sig..."  
  }
  ```
- Request (nächste Seite): `GET /api/v1/inbox/items?cursor=<next>` mit demselben `X-Tenant`.
