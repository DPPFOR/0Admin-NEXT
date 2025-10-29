# Mahnwesen KPIs & Bounce Operations

## Datenquellen & Architektur

- **Primärquelle:** `artifacts/reports/mahnwesen/<tenant>/` (Outbox `sent.json`, Audit `approvals.json`, Bounce-Inbox/Blocklist)
- **Optional:** Brevo Events, DB-Views (integrierbar über `KpiDataSource`/`BounceReconciler` Interfaces)
- **Zeitzone:** Europe/Berlin (Berücksichtigung von Sommer-/Winterzeit über `zoneinfo`)
- **Scheduler:** Täglicher Run 07:30 CET (cron/systemd) → `tools/operate/kpi_engine.py`, `tools/operate/bounce_reconcile.py`

## KPI-Report Felder

| Feld | Beschreibung |
| --- | --- |
| `overdue_total` | Anzahl offener Rechnungen laut Overdue-Provider |
| `notices_created` | Erstellte Mahnungen (Audit + Outbox) |
| `notices_sent` | Erfolgreich dispatchte Mahnungen |
| `errors` | Fehlgeschlagene Dispatches/Audit-Fehler |
| `hard_bounces` / `soft_bounces` | Bounce-Zähler je Tenant |
| `escalations` | Anzahl S3-Eskalationen |
| `retry_depth` / `dlq_depth` | Warteschlangenstände (Ops-Metriken) |
| `error_rate` | `errors / max(1, notices_created)` |
| `cycle_time_median_hours` | Median von Request→Send (Audit), `null` falls keine Paare |
| `timezone` | Fix auf `Europe/Berlin` |

Artefakte pro Tag: `YYYY-MM-DD.json`, `YYYY-MM-DD.md`, `YYYY-MM-DD_summary.md`

## Bounce-Reconcile Regeln

1. Hard Bounce → sofort `status=hard`, Blocklist.
2. Soft Bounce → 3 Versuche binnen 72h, danach Promotion zu `hard`.
3. Reconcile speichert:
   - `blocklist.json` mit Timestamp + letzter Aktion
   - `bounce_processed.json` (Idempotenz)
   - Log `bounce_reconcile_<ts>.json`
4. Inbox (`bounce_inbox.json`) wird nach Verarbeitung geleert.

## Retention

- KPI-Reports & Summaries ≥ 90 Tage aufbewahren
- Bounce-Protokolle & Blocklisten ≥ 90 Tage, Audit ≥ 365 Tage
- Ältere Artefakte rotierend sichern (S3/Backup) – Prozesse im Ops-Wiki

## Betrieb (Daily 07:30 CET)

1. `python tools/operate/kpi_engine.py --all-tenants --notify`
2. `python tools/operate/bounce_reconcile.py --all-tenants --notify`
3. Summary prüfen (`_summary.md`) & ggf. Slack/SMTP (ENV `SLACK_WEBHOOK`/`SMTP_*`) aktivieren
4. Auffälligkeiten dokumentieren (`error_rate > 1%`, `hard_bounce_rate > 5%`)

### Fehlerbilder

- **Sommerzeit-Shift:** Vergangene AUDIT-Zeiten prüfen; `cycle_time_median` liefert Hinweis.
- **Leere Reports:** Prüfen ob neue Artefakte existieren (`sent.json`, `approvals.json`).
- **Blockliste wächst stark:** Bounce-Inbox kontrollieren, ggf. Soft-Promotion Regeln anpassen.

## Reconcile Aktionen

- Soft→Hard Promotions erzeugen Eintrag im Log + Markdown-Summary.
- Blocklist-Updates idempotent (zweiter Lauf = keine Änderung).
- Entsperren nur via Ops-Freigabe (Blocklist-File händisch anpassen, Reconcile bestätigt Status).

## Hooks & Erweiterung

- `KpiDataSource`/`BounceEvent` können erweitert werden (z. B. DB-Reads, Webhooks).
- Notifier unterstützt Slack-Webhooks (`SLACK_WEBHOOK`) und STDOUT. SMTP skeleton vorbereitet (TODO B4).

---

**Hinweis:** Backout per Kill-Switch wirkt weiterhin lokal (`operate_state.json`), nicht global.

