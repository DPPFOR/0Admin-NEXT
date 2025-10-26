# Inbox Read API

Diese Read-Only API stellt die normalisierten Daten aus dem Inbox-Read-Model (Views auf `inbox_parsed`) zur Verfügung. Alle Endpunkte sind GET-only, benötigen eine `tenant`-UUID und liefern ausschließlich entpersonalisierte Informationen – keine Roh-Artefakte, keine Pfade.

## Endpunkte

### GET `/inbox/read/invoices`
- **Query-Parameter**
  - `tenant` *(UUID, Pflicht)*
  - `limit` *(0–100, Default 50)*
  - `offset` *(>=0, Default 0)*
- **Antwort**: Liste von Invoices (neueste zuerst), Felder u. a. `id`, `tenant_id`, `content_hash`, `amount`, `invoice_no`, `due_date`, `quality_status`, `confidence`, `flags`, `mvr_preview`, `mvr_score`, `created_at`.
- **Header**: `X-Total-Count` = Anzahl der gelieferten Einträge.

**Beispiel**
```json
[
  {
    "id": "9e5c77d4-9e8f-4d9d-a148-e3056f870001",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "content_hash": "invoice-hash-accepted",
    "amount": 250.0,
    "invoice_no": "INV-2025-0001",
    "due_date": "2025-01-15",
    "quality_status": "accepted",
    "confidence": 95.0,
    "flags": {"enable_ocr": false},
    "mvr_preview": false,
    "mvr_score": null,
    "created_at": "2025-01-01T12:00:00+00:00"
  }
]
```

### GET `/inbox/read/payments`
- **Query-Parameter**
  - `tenant` *(UUID, Pflicht)*
  - `limit` *(0–100, Default 50)*
  - `offset` *(>=0, Default 0)*
- **Antwort**: Liste von Zahlungen mit Feldern wie `amount`, `currency`, `counterparty`, `payment_date`, `quality_status`, `confidence`, `flags`, `mvr_preview`, `mvr_score`, `created_at`.
- **Header**: `X-Total-Count` = Anzahl der gelieferten Einträge.

**Beispiel**
```json
[
  {
    "id": "bfaf9246-5d35-435f-a389-67e86561733f",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "content_hash": "payment-good-0001",
    "amount": 250.0,
    "currency": "EUR",
    "counterparty": "ACME Bank",
    "payment_date": "2025-02-15",
    "quality_status": "accepted",
    "confidence": 100.0,
    "flags": {"mvr_preview": true},
    "mvr_preview": true,
    "mvr_score": "0.00",
    "created_at": "2025-02-15T10:00:01+00:00"
  }
]
```

### GET `/inbox/read/review`
- Gleiche Parameter wie `/inbox/read/invoices`.
- Liefert alle Items mit Qualitätsstatus `needs_review` bzw. `rejected`.

**Beispiel**
```json
[
  {
    "id": "44d4d4d4-0000-0000-0000-000000000111",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "doc_type": "invoice",
    "quality_status": "needs_review",
    "confidence": 45.0,
    "created_at": "2025-01-01T11:55:00+00:00",
    "content_hash": "invoice-hash-review"
  }
]
```

### GET `/inbox/read/summary`
- Parameter: `tenant` (Pflicht).
- Antwort: Aggregierte Kennzahlen (`cnt_items`, `cnt_invoices`, `cnt_payments`, `cnt_other`, `cnt_needing_review`, `cnt_mvr_preview`, `avg_confidence`, `avg_mvr_score`).
- 404 falls keine Daten für den Tenant vorliegen.

**Beispiel**
```json
{
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "cnt_items": 3,
  "cnt_invoices": 2,
  "cnt_payments": 1,
  "cnt_other": 0,
  "cnt_needing_review": 1,
  "cnt_mvr_preview": 1,
  "avg_confidence": 78.3,
  "avg_mvr_score": 0.0
}
```

## Hinweise
- **Read-only**: Alle Endpunkte greifen ausschließlich auf Views (`v_invoices_latest`, `v_payments_latest`, `v_items_needing_review`, `v_inbox_by_tenant`) zu.
- **Keine PII**: Daten sind normalisiert; Payloads und Original-Artefakte werden nicht ausgegeben.
- **Rate Limits / Caching**: Frontend- oder Agent-Konsumenten sollten clientseitig cachen und mit moderaten Limits arbeiten (z. B. `limit<=50`).
- **Tracing**: Optionaler Header `X-Trace-ID` wird ins Logging übernommen.

## Flock-Integration (Beispiel)

```python
from tools.flows import flock_samples

tenant = "00000000-0000-0000-0000-000000000001"
base_url = "http://localhost:8000"

invoices = flock_samples.fetch_invoices(tenant, base_url=base_url)
review = flock_samples.fetch_review_queue(tenant, base_url=base_url)

print(invoices)
print(review)
```

Siehe auch `tools/flows/flock_samples.py` für einen CLI-Aufruf sowie `tools/flows/query_read_model.py` für direkte SQL-Queries.
