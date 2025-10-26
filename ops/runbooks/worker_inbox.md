# Worker: Inbox Parsing v1

Zweck: Verarbeitet `InboxItemValidated v1.0` aus `event_outbox` zu `parsed_items` (optional `chunks`) und emittiert Folge-Events `InboxItemParsed` bzw. `InboxItemParseFailed`.

- Start/Stop
- Einmaliger Durchlauf: `python -c "from agents.inbox_worker.runner import run_once; run_once()"` (Batch)
- Polling-Loop: `python -c "from agents.inbox_worker.runner import run_forever; run_forever(service_mode=True)"`
- `WORKER_POLL_INTERVAL_MS` steuert den Schlaf zwischen Leerlauf-Batches.
- ENV: `DATABASE_URL`, `WORKER_BATCH_SIZE`, `WORKER_POLL_INTERVAL_MS`, `PARSER_MAX_BYTES`, `PARSER_CHUNK_THRESHOLD_BYTES`, `PARSER_RETRY_MAX`, `PARSER_BACKOFF_STEPS`.
- Status-Übergänge Outbox: `pending → processing → sent|failed`; Felder `attempt_count`, `next_attempt_at` werden bei Retries fortgeschrieben.

Ablauf
- Lease: Outbox-Events (`InboxItemValidated`) mit `status=pending` werden auf `processing` gesetzt.
- Idempotenz: Eintrag in `processed_events (tenant_id,event_type,idempotency_key)` verhindert Doppelverarbeitung.
- Parsing: MIME→doc_type; heuristische Extraktion (Rechnungsnr., Betrag, Fälligkeit). Unbekannt → `doc_type=unknown` ohne Fehler.
- Persistenz: `parsed_items.payload_json` speichert nur Extrakt (keine Rohbytes). Optional `chunks` bei großen Extrakten.
- Status: `inbox_items.validated→parsed|error`; Outbox-Status `sent|failed`.
- Events: `InboxItemParsed v1.0` oder `InboxItemParseFailed v1.0` in `event_outbox` (Idempotenz via `(tenant_id,idempotency_key,event_type)`).
- Retry/Backoff: bei `io_error` → Backoff (5s, 30s, 300s) bis max Versuche, danach `dead_letters`.

Continuous Runner (optional)
- Empfehlung für 24/7-Betrieb: Systemd-Timer/Unit, der `run_once()` alle `WORKER_POLL_INTERVAL_MS` ausführt.
- Beispiel-Polling (Pseudo): `while true: n=run_once(); sleep(WORKER_POLL_INTERVAL_MS/1000)` (in eigenem Supervisor, nicht im Repo enthalten).

Metriken
- `parsed_total++`, `parse_failures_total++`, `chunk_bytes_total+=`, `parse_duration_ms` (Histogram).

Fehlerbilder
- `validation_error|unsupported_mime|parse_error` → nicht-retriable, `error` + ParseFailed.
- `io_error` (FS/DB) → retriable bis Limit, danach DLQ.

Hinweise
- Keine PII/Rohinhalte in Logs/Events.
- Storage: v1 unterstützt nur `file://` URIs; andere Schemata führen zu `io_error` (retriable bis DLQ).
- systemd (Beispiel)
  - Service (`/etc/systemd/system/inbox-worker.service`):
    ```ini
    [Unit]
    Description=0Admin Inbox Worker
    After=network.target

    [Service]
    Type=simple
    ExecStart=/usr/bin/python -c "from agents.inbox_worker.runner import run_forever; run_forever(service_mode=True)"
    Restart=on-failure
    RestartSec=5
    LimitNOFILE=65536
    EnvironmentFile=/etc/0admin/env

    [Install]
    WantedBy=multi-user.target
    ```
  - Timer-Alternative: rufen Sie `run_forever(service_mode=False)` auf, der Prozess beendet sich mit Exit 0 bei Leerlauf (geeignet für Oneshot-Timer).

Crontab (Timer-Mode)
- Kollisionsschutz: keine parallelen Läufe zulassen (z. B. via `flock`).
- Beispiel (alle 2 Minuten, Timer-Mode):
  ```cron
  */2 * * * * /usr/bin/flock -n /var/run/0admin/inbox-worker.lock \
    /usr/bin/python -c "from agents.inbox_worker.runner import run_forever; run_forever(service_mode=False)" \
    >> /var/log/0admin/inbox-worker-cron.log 2>&1
  ```
  - Hinweis: `WORKER_POLL_INTERVAL_MS` hat im Timer-Mode keine Wirkung; der Prozess beendet sich bei Leerlauf mit Exit 0.
