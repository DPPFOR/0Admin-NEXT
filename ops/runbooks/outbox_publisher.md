# Outbox Publisher v1

Zweck: Zuverlässiges Publishen von Outbox-Events mit Backoff/DLQ und pluggable Transports (stdout/webhook).

Start/Modus
- Einmaliger Durchlauf: `python -c "from agents.outbox_publisher.runner import run_once; run_once()"`
- Polling-Loop: `python -c "from agents.outbox_publisher.runner import run_forever; run_forever(service_mode=True)"`
- `PUBLISH_POLL_INTERVAL_MS` steuert den Schlaf zwischen Leerlauf-Batches.

ENV
- Transport: `PUBLISH_TRANSPORT=stdout|webhook`
- Batch/Timing: `PUBLISH_BATCH_SIZE`, `PUBLISH_POLL_INTERVAL_MS`
- Backoff/Retry: `PUBLISH_BACKOFF_STEPS` (z. B. "5,30,300"), `PUBLISH_RETRY_MAX`
- Webhook: `WEBHOOK_URL` (https only), `WEBHOOK_TIMEOUT_MS`, `WEBHOOK_SUCCESS_CODES` (z. B. "200-299"), `WEBHOOK_HEADERS_ALLOWLIST` (CSV `Key=Value`)

Policy/Sicherheit
- TLS strict (verify=True), keine Redirects.
- Nur `https://` URLs erlaubt; `http://` führt zu `failed` + DLQ.
- Keine Secrets/Headers in Logs; Header-Injektion ausschließlich über Allowlist.

Status/Backoff
- Status: `pending → processing → sent|failed`.
- Bei Fehler: `attempt_count++`, `next_attempt_at` per Backoff; nach `PUBLISH_RETRY_MAX` → `dead_letters`, original Outbox `failed`.

Metriken
- `publisher_attempts_total`, `publisher_sent_total`, `publisher_failures_total`.
- `publisher_lag_ms` (now − created_at), `publish_duration_ms`.

Troubleshooting
- Beobachte Lag (`publisher_lag_ms`); passe Batch/Interval an.
- DLQ per Ops-API (U5-R) listen und ggf. replayen (mit Vorsicht).
- systemd (Beispiel)
  - Service (`/etc/systemd/system/outbox-publisher.service`):
    ```ini
    [Unit]
    Description=0Admin Outbox Publisher
    After=network.target

    [Service]
    Type=simple
    ExecStart=/usr/bin/python -c "from agents.outbox_publisher.runner import run_forever; run_forever(service_mode=True)"
    Restart=on-failure
    RestartSec=5
    LimitNOFILE=65536
    EnvironmentFile=/etc/0admin/env

    [Install]
    WantedBy=multi-user.target
    ```
  - Timer-Alternative (`outbox-publisher.timer` + `outbox-publisher@.service`) für batched Betrieb: rufen Sie `run_forever(service_mode=False)` auf, Exit 0 bei Leerlauf.

Crontab (Timer-Mode)
- Kollisionsschutz: keine parallelen Läufe zulassen (z. B. via `flock`).
- Beispiel (jede Minute, Timer-Mode, Exit 0 bei Idle):
  ```cron
  * * * * * /usr/bin/flock -n /var/run/0admin/outbox-publisher.lock \
    /usr/bin/python -c "from agents.outbox_publisher.runner import run_forever; run_forever(service_mode=False)" \
    >> /var/log/0admin/outbox-publisher-cron.log 2>&1
  ```
  - Hinweis: `PUBLISH_POLL_INTERVAL_MS` hat im Timer-Mode keine Wirkung; der Prozess beendet sich bei Leerlauf mit Exit 0.
