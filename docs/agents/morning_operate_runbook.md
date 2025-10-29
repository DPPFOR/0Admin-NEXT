# Morning Operate Runbook — Mahnwesen

## Zweck

Täglicher Einlauf (empfohlen 07:30 CET) zur Bewertung des Mahnwesen-Canary-Rollouts: KPI sammeln, Entscheidung treffen, Rollout anpassen, Bounce-Blockliste pflegen und Ergebnisse dokumentieren.

## Ablauf (pro Tenant)

1. **KPI Aggregation** (`tools/operate/kpi_engine.py`)
   - Erstellt/aktualisiert `YYYY-MM-DD.json` & `.md`
   - Quelle: lokale Artefakte (Approvals, Outbox, Blocklist)
2. **Canary Decision** (`tools/operate/canary_engine.py`)
   - Schwellen (Standard): Fehler ≤ 2 %, Hard Bounce ≤ 5 %, DLQ ≤ 10, Retry ≤ 50, min. 3 Dispatches
   - Ergebnis: HOLD | GO_25 | GO_50 | GO_100 | BACKOUT (Begründungen im Artefakt)
3. **Rollout Controller** (`tools/operate/canary_rollout.py`)
   - Step-Up 10→25→50→100 % oder Kill-Switch (BACKOUT)
   - Idempotent: keine doppelten Änderungen bei gleichen Zuständen
4. **Bounce Reconcile** (`tools/operate/bounce_reconcile.py`)
   - Hard Bounce → sofort blocken
   - Soft Bounce → 3 Versuche / 72 h, danach Hard
5. **Summary** (`YYYY-MM-DD_morning_summary.md`)
   - Enthält KPI-Werte, Entscheidung, Rollout-Aktion, Bounce-Änderungen, Overrides/Warnungen

## Werkzeuge

- Orchestrator: `python tools/operate/morning_operate.py --tenant <id>`
- Alle Tenants: `--all-tenants`
- Dry-Run: `--dry-run` (keine Rollout-Änderung, Summary wird dennoch geschrieben)
- VS Code Tasks:
  - „Operate: Morning Run (Tenant)“
  - „Operate: Morning Run (All Tenants)“
  - „Operate: Morning Run – Dry-Run“

## Artefakte

- KPI: `artifacts/reports/mahnwesen/<tenant>/<YYYY-MM-DD>.json|.md`
- Decision: `…/canary/<timestamp>_decision.json|.md`
- Rollout-Log: `…/canary/<timestamp>_rollout_log.json`
- Operate-State: `…/operate/operate_state.json`
- Bounce: `…/ops/blocklist.json`, `…/ops/bounce_reconcile_<ts>.json`
- Summary: `…/<YYYY-MM-DD>_morning_summary.md`

## Backout & Kill-Switch

- Entscheidung „BACKOUT“ ⇒ Kill-Switch ON, Quote ≤ 10 %
- Operate-State protokolliert Timestamp & Trace-ID
- Rollout bleibt gestoppt, bis neue Entscheidung „GO“ getroffen wird

## Troubleshooting

- **LOW SAMPLE**: < 3 Dispatches – Canary hält automatisch; erneut prüfen nach höherem Volumen
- **Schwellenverletzung**: Decision begründet (Error/Bounce/DLQ). Ursachen analysieren, ggf. Kill-Switch aktiviert lassen
- **Overrides aktiv**: Summary listet abweichende Thresholds (ENV `CANARY_THRESHOLD_*`); vor Go-Live wieder rücksetzen
- **Bounce-Anstieg**: `blocklist.json` und `bounce_reconcile_<ts>.json` prüfen, Ursachen (z. B. Provider) abklären

## Go-Live Checkliste (Morning)

- ✅ KPI Summary ohne kritische Warnungen
- ✅ Decision ≠ BACKOUT (oder begründet)
- ✅ Rollout-Historie plausibel (Step-Up nur einmal pro Tag)
- ✅ Bounce-Blocklist unter Kontrolle (keine massiven Hard-Bounces)
- ✅ Kill-Switch = OFF (sofern kein Incident)

## Hinweise

- DNS/Absender bleiben log-only (vgl. `sender_dns_checklist.md`)
- Retention: KPI & Rollout-Logs ≥ 90 d, Audit ≥ 365 d, Logs 30 d
- Redaction-Probe (`tools/operate/redaction_probe.py`) regelmäßig laufen lassen

