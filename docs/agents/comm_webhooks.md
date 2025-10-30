# Brevo Webhooks – Setup & Troubleshooting

**Version:** 1.0  
**Letzte Aktualisierung:** 2025-01-15  
**Status:** Production-Ready

---

## Überblick

Dieses Dokument beschreibt die Einrichtung und den Betrieb des Brevo-Webhook-Empfängers für E-Mail-Tracking-Events (delivered, bounces, opens, clicks). Der Webhook-Receiver validiert eingehende Requests via HMAC-SHA256, mappt Events zu normalisierten CommEvent-Strukturen und persistiert sie im WORM-light Format.

---

## Komponenten

- **Webhook Receiver:** FastAPI-Server unter `/operate/brevo/webhook` (separater Server)
- **Event Mapping:** Brevo → Normierte CommEvent-Struktur
- **Event Persistenz:** Datei-basiert in `artifacts/events/<tenant>/<YYYYMMDD>/`
- **Idempotenz:** Provider|Event-ID basiert, Duplikate werden automatisch gedroppt

---

## Umgebungsvariablen

### Erforderlich

```bash
# Brevo Webhook Secret (für HMAC-Verifikation)
export BREVO_WEBHOOK_SECRET="your-webhook-secret-key"

# Standard-Tenant (Fallback wenn nicht im Header/Payload)
export TENANT_DEFAULT="00000000-0000-0000-0000-000000000001"
```

### Optional

```bash
# Brevo API-Key (für Outbound-Versand)
export BREVO_API_KEY="xkeysib-..."
export BREVO_SENDER_EMAIL="noreply@0admin.com"
export BREVO_SENDER_NAME="0Admin"
```

---

## Setup

### 1. Webhook-Secret konfigurieren

Das Webhook-Secret muss in Brevo konfiguriert werden und mit `BREVO_WEBHOOK_SECRET` übereinstimmen.

**In Brevo Dashboard:**
1. Settings → Webhooks
2. Webhook-Secret generieren oder bestehendes verwenden
3. Secret in `.env` als `BREVO_WEBHOOK_SECRET` setzen

### 2. Webhook-URL konfigurieren

**In Brevo Dashboard:**
- URL: `https://your-domain.com/operate/brevo/webhook`
- Method: POST
- Events: delivered, soft_bounce, hard_bounce, blocked, spam, invalid, opened, click

### 3. Lokaler Test-Server starten

```bash
# Via VSCode Task: "Comm: Run Webhook (local)"
# Oder direkt:
uvicorn tools.operate.brevo_webhook:app --port 8787 --reload
```

Der Server läuft dann auf `http://localhost:8787`.

---

## Nginx-Konfiguration (Hinweise)

Für Production-Betrieb hinter Nginx mit TLS:

```nginx
location /operate/brevo/webhook {
    proxy_pass http://127.0.0.1:8787;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Wichtig: Body für HMAC-Verifikation weiterleiten
    proxy_pass_request_body on;
    proxy_set_header Content-Length $content_length;
    
    # Timeout für langsame Requests
    proxy_read_timeout 30s;
}
```

**Wichtig:** Der raw Body muss für HMAC-Verifikation verfügbar sein. Nginx sollte den Body nicht modifizieren.

---

## Event-Persistenz

### Struktur

```
artifacts/events/
  <tenant_id>/
    <YYYYMMDD>/
      event-<uuid>.json       # Einzelne Events
      events.ndjson           # NDJSON-Stream (append-only)
      .idempotency-<YYYYMMDD>.lock  # Idempotenz-Cache
```

### Event-Format

Jedes Event wird als JSON mit folgenden Feldern gespeichert:

```json
{
  "event_id": "uuid",
  "event_type": "delivered",
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "message_id": "brevo-msg-12345",
  "recipient": "user@example.com",
  "reason": null,
  "ts": "2025-01-15T10:30:00+00:00",
  "metadata": {
    "tag": "invoice-notification",
    "sending_ip": "192.168.1.1"
  },
  "provider": "brevo",
  "provider_event_id": "brevo-12345",
  "idempotency_key": "brevo|brevo-12345"
}
```

### Idempotenz

- Idempotenz-Key: `provider|event_id` (z.B. `brevo|12345`)
- Duplikate werden automatisch erkannt und gedroppt
- Pro Tag: In-Memory-Cache + Lockfile

---

## Event-Replay

Events können aus NDJSON-Dateien replayed werden:

```bash
# Via VSCode Task: "Comm: Replay Events"
# Oder direkt:
python tools/operate/brevo_events_replay.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --date 20250115 \
  --type delivered \
  --dry-run
```

**Optionen:**
- `--tenant`: Tenant ID (erforderlich)
- `--date`: Datum-Filter (YYYYMMDD, optional)
- `--type`: Event-Typ-Filter (optional)
- `--dry-run`: Keine Persistenz, nur Anzeige

---

## Troubleshooting

### 401 Unauthorized

**Problem:** HMAC-Signatur ungültig

**Lösung:**
1. Prüfe `BREVO_WEBHOOK_SECRET` in `.env`
2. Prüfe `X-Brevo-Signature` Header-Format (`sha256=<hex>`)
3. Prüfe, ob Body vor Parsing für HMAC verwendet wird

### 400 Bad Request

**Problem:** Ungültiger Payload

**Lösung:**
1. Prüfe JSON-Format des Payloads
2. Prüfe erforderliche Felder (`event`, `date`)
3. Prüfe Event-Typ (muss unterstützt sein)

### Events werden nicht persistiert

**Problem:** Persistenz schlägt fehl

**Lösung:**
1. Prüfe Schreibrechte für `artifacts/events/`
2. Prüfe Tenant-ID (gültiges UUID-Format)
3. Prüfe Logs für Fehlerdetails

### Duplikate werden nicht erkannt

**Problem:** Idempotenz funktioniert nicht

**Lösung:**
1. Prüfe `provider_event_id` oder `message_id` im Payload
2. Prüfe Lockfile-Pfad (`artifacts/events/<tenant>/<date>/.idempotency-*.lock`)
3. Prüfe, ob Events denselben Idempotenz-Key generieren

### Tenant-ID nicht gefunden

**Problem:** Tenant-ID fehlt im Payload/Header

**Lösung:**
1. Prüfe `X-Tenant-ID` Header
2. Prüfe Payload-Metadata (`metadata.tenant_id`)
3. Fallback auf `TENANT_DEFAULT` wird verwendet

---

## Unterstützte Eventtypen

| Event-Typ | Beschreibung | Felder |
|-----------|-------------|--------|
| `delivered` | E-Mail erfolgreich zugestellt | message_id, email, tag |
| `soft_bounce` | Temporärer Bounce | message_id, email, reason |
| `hard_bounce` | Permanenter Bounce | message_id, email, reason |
| `blocked` | E-Mail blockiert | message_id, email, reason |
| `spam` | Als Spam markiert | message_id, email, reason |
| `invalid` | Ungültige E-Mail-Adresse | message_id, email, reason |
| `opened` | E-Mail geöffnet | message_id, email, ip, user_agent |
| `click` | Link geklickt | message_id, email, link, ip, user_agent |

---

## PII-Redaction

- E-Mail-Adressen werden in Logs maskiert
- PII wird nicht in Event-Dateien gespeichert (nur in `recipient` Feld)
- Logs verwenden JSON-Format mit PII-Redaction

---

## Monitoring & Metriken

**Logs:**
- JSON-Format mit `trace_id`, `tenant_id`, `event_type`
- PII-redacted

**Dateien:**
- Event-Dateien: `artifacts/events/<tenant>/<date>/event-*.json`
- NDJSON-Stream: `artifacts/events/<tenant>/<date>/events.ndjson`

---

## Weiterführende Informationen

- **Brevo Webhook-Dokumentation:** https://developers.brevo.com/reference/webhooks
- **Event-Outbox-Policy:** `.cursor/rules/Event-Outbox-Policy-Ereignisrichtlinie.mdc`
- **Coding-Agent-Policy:** `.cursor/rules/Coding-Agent-Policy.mdc`

