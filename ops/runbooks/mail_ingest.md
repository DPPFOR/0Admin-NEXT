# Mail-Ingest v1 (IMAP/Graph)

Zweck: E-Mails aus Postfächern abrufen, Attachments extrahieren und in den Inbox-Flow einspeisen (`InboxItemValidated v1.0`).

Start/Modus
- Pull-Job (kein öffentlicher HTTP-Endpunkt), on-demand oder Polling-Loop per ENV.
- Provider via `MAIL_PROVIDER=imap|graph` wählbar.

ENV
- Allgemein: `MAILBOX_NAME`, `MAIL_BATCH_LIMIT`, `MAIL_SINCE_HOURS`, `MAIL_POLL_INTERVAL_MS` (0 = kein Loop)
- IMAP: `IMAP_HOST`, `IMAP_PORT`, `IMAP_SSL=true`, `IMAP_USERNAME`, `IMAP_PASSWORD`
- Graph: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_USER_ID`
- Limits: `MAX_ATTACH_MB` (alias `MAX_UPLOAD_MB`), `MIME_ALLOWLIST`

Ablauf
- Pro Nachricht: Attachments extrahieren (PDF, PNG/JPG, CSV/XLSX, JSON/XML), Body ignorieren.
- Validierung: Größe ≤ `MAX_ATTACH_MB`, MIME-Allowlist, serverseitige Erkennung (Endungen ignorieren).
- Persistenz: `file://` Storage (atomisch), DB speichert `uri + content_hash` (keine Blobs in DB).
- Event: `InboxItemValidated` (`schema_version="1.0"`), Idempotenz-Key = `message_id:content_hash`.

Observability
- Logs (keine PII): `trace_id`, `tenant_id`, `mailbox`, `message_id`, `attach_count`, `processed_count`, `duplicates`, `duration_ms`.
- Metriken: `mail_messages_total`, `mail_attachments_total`, `mail_ingest_failures_total`, `mail_ingest_duration_ms`.

Compliance
- IMAP: TLS verpflichtend; keine Plain-IMAP.
- Graph: Least-Privilege; keine Token/Headers in Logs.
- PII: Keine Adressen/Namen/Betreff/Body in Logs oder Events. Erlaubt: `message_id`, `mailbox`, Hashes, Größen, MIME, Zeitstempel.

Hinweise
- v1 unterstützt nur `file://` Storage. `sb://` ist nicht unterstützt.
- Tests/CI laufen egress-frei (Provider werden gemockt).
