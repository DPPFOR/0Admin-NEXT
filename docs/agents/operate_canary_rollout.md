# Mahnwesen Canary Rollout Playbook

## Ziel

Schrittweise Freigabe der Mahnwesen-Dispatches (10 % → 25 % → 50 % → 100 %) anhand objektiver Kennzahlen. Entscheidungen sind nachvollziehbar, idempotent und jederzeit rückbaubar (Kill-Switch).

## Datenquellen

- KPI JSON: `artifacts/reports/mahnwesen/<tenant>/<YYYY-MM-DD>.json`
- Bounce/Blocklist: `artifacts/reports/mahnwesen/<tenant>/ops/blocklist.json`
- Operate-State: `artifacts/reports/mahnwesen/<tenant>/operate/operate_state.json`
- Decision-/Rollout-Logs: `artifacts/reports/mahnwesen/<tenant>/canary/*.json|.md`

## Werkzeuge

- Entscheidung: `python tools/operate/canary_engine.py --tenant <id> [--date YYYY-MM-DD]`
- Rollout: `python tools/operate/canary_rollout.py --tenant <id> [--decision-file path]`
- VS-Code Tasks: „Operate: Canary Decide (Tenant)“, „Operate: Canary Rollout (Tenant)“, „Operate: Canary Full Cycle (Decide→Rollout)“

## Schwellenwerte (Standard)

| Kennzahl | Schwellwert | Quelle |
| --- | --- | --- |
| Fehlerquote | ≤ 2 % | KPI `error_rate` |
| Hard-Bounce-Rate | ≤ 5 % | KPI `hard_bounces / notices_sent` |
| DLQ-Tiefe | ≤ 10 | KPI `dlq_depth` |
| Retry-Tiefe | ≤ 50 | KPI `retry_depth` |
| Mindestvolumen | ≥ 3 Dispatches | KPI `notices_sent` |

Per Tenant übersteuerbar via ENV `CANARY_THRESHOLD_*`.

## Entscheidungslogik

1. KPIs & Blocklist lesen
2. Grenzwerte prüfen → Gründe sammeln
3. Ausgangsstate (aktuelle Quote, Kill-Switch) berücksichtigen
4. Ergebnis:
   - **GO_25 / GO_50 / GO_100**: Schwellen erfüllt → nächster Step
   - **HOLD**: Schwellen verletzt oder Volumen zu gering
   - **BACKOUT**: Schwere Verletzung (Schwellen >> Grenzwert) → Kill-Switch empfohlen
5. Entscheidung wird in JSON + Markdown dokumentiert (Zeitstempel & Gründe)

## Rollout & Idempotenz

1. Letzte Entscheidung laden (`*_decision.json`)
2. State lesen (`operate_state.json`)
3. Aktion anwenden:
   - GO → Quote erhöhen (10→25→50→100), Kill-Switch deaktivieren
   - HOLD → keine Änderung
   - BACKOUT → Kill-Switch aktivieren, Quote auf 10 %
4. Neues State-File schreiben (mit Verlauf) + Rollout-Log `*_rollout_log.json`
5. Wiederholter Lauf mit gleicher Entscheidung ändert nichts (`changed=false`)

## Backout-Regeln

- Entscheidung **BACKOUT** setzt Kill-Switch ON + begründet
- Rollout-Log enthält Trace-ID & Gründe
- Wiedereinstieg erst nach Review + neuer Entscheidung

## Run-Anleitung (Daily 07:30 CET)

1. `python tools/operate/kpi_engine.py --tenant <id>` (falls noch nicht geschehen)
2. `python tools/operate/canary_engine.py --tenant <id>` → JSON/MD prüfen
3. Bei GO: `python tools/operate/canary_rollout.py --tenant <id>`
4. Bei HOLD: Ursachen analysieren (KPIs, Alerts, Blocklist)
5. Bei BACKOUT: Kill-Switch bestärken, Incident eröffnen

## Troubleshooting

- **HOLD wegen Volumen**: Auf ausreichende Dispatches warten (≥ 3)
- **HOLD wegen Bounces**: Bounce-Reconcile prüfen (`blocklist.json`)
- **BACKOUT**: Ursachen dokumentieren, Kill-Switch bleibt bis Entscheidung „GO“
- **State inkonsistent**: `operate_state.json` Historie prüfen, Entscheide neu schreiben

## Hinweise

- DNS/Absender (SPF/DKIM/DMARC) log-only prüfen: `tools/operate/sender_dns_check.py`
- DMARC RUA Postfach & Brevo Sender-Verifikation operativ abhaken (Doku)
- Retention: KPI & Rollout-Logs ≥ 90 d, Audit ≥ 365 d, Logs 30 d

