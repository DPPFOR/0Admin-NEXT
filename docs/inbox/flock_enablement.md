# Flock Enablement (Read-Only)

Flock-Agenten lesen Inbox-Daten ausschließlich über die Read-API. Der Zugriff ist strikt tenant-isoliert und akzeptiert kein Schreiben.

## Authentifizierung & Mandanten-Trennung

- Jeder Request **muss** den Header `X-Tenant-ID` mit einer gültigen UUID enthalten.
- Fehlender oder ungültiger Header führt zu `422`. Daten anderer Tenants werden niemals ausgeliefert.
- Rate-Limits & Backoff: bei `429` oder `5xx` sollte der Client mit exponentiellem Backoff (bis 3 Versuche) reagieren.

## Endpunkte & Parameter

| Endpoint | Beschreibung | Filter |
|----------|--------------|--------|
| `GET /inbox/read/invoices` | Letzte Rechnungen | `limit` (≤100), `offset`, `status` (`accepted`, `needs_review`, `rejected`), `min_conf` (0–100) |
| `GET /inbox/read/payments` | Letzte Zahlungen | wie oben |
| `GET /inbox/read/review` | Review-Queue (alle Doctypes) | wie oben |
| `GET /inbox/read/summary` | Aggregat pro Tenant | keine Filter |

Antworten der Listen-Endpunkte sind JSON-Objekte: `{"items": [...], "total": n, "limit": x, "offset": y}`. Felder `quality_status`, `confidence`, `flags`, `mvr_score` und `mvr_preview` sind zentrale Signale für Beurteilungen.

## Curl-Beispiele

```bash
curl -s -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
     "http://localhost:8000/inbox/read/invoices?status=accepted&min_conf=80&limit=25"
```

```bash
curl -s -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
     "http://localhost:8000/inbox/read/review?limit=10&offset=0"
```

```bash
curl -s -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
     "http://localhost:8000/inbox/read/summary"
```

## Python-Client (Sample)

```python
from backend.clients.flock_reader import FlockReadClient

client = FlockReadClient(base_url="http://localhost:8000")
tenant_id = "00000000-0000-0000-0000-000000000001"

invoices = client.get_invoices(tenant_id, status="accepted", min_conf=80)
for invoice in invoices["items"]:
    print(invoice["invoice_no"], invoice["quality_status"], invoice["confidence"])

summary = client.get_summary(tenant_id)
print("Needing review:", summary["cnt_needing_review"])
```

## Hinweise

- `limit` darf maximal 100 betragen; höhere Werte werden abgelehnt.
- `flags` enthalten strukturierte Zusatzinformationen (z. B. `mvr_preview`).
- `confidence` wird als Float (0–100) geliefert. Für Filter stets ganze Zahlen nutzen.
- Fehlversuche (`400+`) enthalten JSON-Fehlertexte; Clients sollten diese loggen.
- Weitere Details zu Feldern und Tabellen: `docs/inbox/read_api.md`, `docs/inbox/read_model.md`.
