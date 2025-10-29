# Operate Canary Playbook – Mahnwesen v1

## Schwellen & KPIs

- **Success Rate:** ≥ 97 % (Rolling 60 min)
- **Error Rate:** ≤ 1 %
- **DLQ Depth:** 0 (jede Nachricht im DLQ blockiert das Upgrade)
- **Retry Depth:** ≤ 50 (Warnung), Alarm ab 51
- **Hard Bounce Rate:** ≤ 5 % (24 h)
- **Brevo Lag:** ≤ 2 min durchschnittlich

## Entscheidungsrahmen (10 % → 25 % → 100 %)

1. **Dateneinsammeln (Operate CLI):**
   - `tools/operate/alert_emitter.py` (Dry-Run) → Schwellenprüfung/Prototyp.
   - `tools/operate/canary_decision.py --success-rate …` → liefert „GO 25 %“ oder „HOLD“ inkl. Begründung.
2. **Go-Entscheidung:** Nur wenn alle Kennzahlen innerhalb des Fensters liegen und kein offener Incident vorliegt.
3. **Hold / Backout:**
   - Sofort `tools/operate/kill_switch.py --reason … --trace-id …` ausführen (Kill-Switch idempotent).
   - Alarm in Slack/STDOUT posten (Error, DLQ, Retry, Bounce).

## Beispiel-Alarme (STDOUT / JSON)

```
python tools/operate/alert_emitter.py --tenant <TENANT> --metric error_rate --value 0.035 --trace-id alert-err
python tools/operate/alert_emitter.py --metric dlq_depth --value 12 --tenant <TENANT> --trace-id alert-dlq
python tools/operate/alert_emitter.py --metric retry_depth --value 72 --tenant <TENANT> --trace-id alert-retry
python tools/operate/alert_emitter.py --metric hard_bounce_rate --value 0.08 --tenant <TENANT> --trace-id alert-bounce
```

Jeder Aufruf erzeugt ein JSON mit `tenant_id`, `trace_id`, `metric`, `threshold`, `value`, `severity` sowie einen Kurztext für Slack/Email.

## Backout-Checkliste

1. **Kill-Switch aktivieren:** `python tools/operate/kill_switch.py --tenant … --reason … --trace-id …`
2. **Outbox Worker stoppen** (falls nötig): systemd-Unit `0admin-outbox-worker` pausieren.
3. **DLQ analysieren:** Grund auflisten, Ticket erstellen.
4. **Kommunikation:** Incident-Channel informieren (Alert-JSON anhängen).

## Tagesroutine (07:30 UTC)

1. `python tools/operate/canary_decision.py --success-rate … --error-rate … --dlq-depth … --hard-bounce-rate …`
2. `python tools/flock/playbook_mahnwesen.py --report-daily`
3. `python tools/operate/alert_emitter.py` (nur bei Grenzwerten) → Alarm testen.
4. Audit-Ordner prüfen (`artifacts/reports/mahnwesen/<tenant>/audit/`).
5. Status im Ops-Log dokumentieren (Go/Hold/Backout + Trace-ID).

---

**Backout-Plan:** Erfolgt innerhalb von 5 Minuten nach Erreichen eines Grenzwerts. Kill-Switch-Einträge sind unter `artifacts/reports/mahnwesen/<tenant>/operate/operate_state.json` nachvollziehbar. Backout per Kill-Switch wirkt lokal im Operate-Flow (`operate_state.json`), nicht als globale Prod-Konfiguration.

