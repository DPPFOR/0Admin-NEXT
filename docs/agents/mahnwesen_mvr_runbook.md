# Mahnwesen MVR Runbook (Manual Verification & Release)

**Version:** 1.0  
**Letzte Aktualisierung:** 2025-10-25  
**Status:** Production-Ready

---

## Überblick

Dieses Runbook beschreibt den operativen Betrieb des Mahnwesen-Systems (Dunning/Reminder) mit Fokus auf MVR (Manual Verification & Release), Idempotenz, Rate-Limits und Daily KPIs.

## Komponenten

- **MVR Preview:** Zeigt versandbereite Mahnungen ohne Versand
- **Approve/Reject:** Manuelle Freigabe/Ablehnung mit Audit-Trail
- **Dispatch:** Versand mit Idempotenz-Check & Rate-Limits
- **Brevo Live:** E-Mail-Versand via Brevo API mit Dry-Run-Toggle
- **Daily KPIs:** Tägliche Aggregation pro Tenant mit JSON/MD-Reports

---

## Umgebungsvariablen

### Brevo (E-Mail-Versand)

```bash
# Brevo API-Key (erforderlich für Live-Versand)
export BREVO_API_KEY="xkeysib-..."

# Absender-Konfiguration
export BREVO_SENDER_EMAIL="noreply@0admin.com"
export BREVO_SENDER_NAME="0Admin"
```

### Rate-Limits & Kill-Switch

```bash
# Rate-Limit pro Tenant (Notices pro Stunde)
export MAHNWESEN_<TENANT_ID>_MAX_NOTICES_PER_HOUR=200

# Kill-Switch (via CLI-Flag --kill-switch)
# Verhindert ALLE Versendungen (0 Events)
```

### Tenant-Spezifische Header

```bash
# Multi-Tenant Header (wird automatisch gesetzt)
X-Tenant-Id: <TENANT_UUID>
```

---

## Workflows

### 1. MVR Preview (Vorschau ohne Versand)

**Zweck:** Zeigt versandbereite Mahnungen für manuelle Prüfung

**Befehl:**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --preview \
  --verbose
```

**VSCode Task:** `MVR: Preview (Tenant)`

**Output:**
```
MVR PREVIEW - NOTICES READY FOR REVIEW
Tenant: 00000000-0000-0000-0000-000000000001
Total Overdue: 42
Stage 1: 15
Stage 2: 20
Stage 3: 7
Notices Created: 42
```

---

### 2. Approve/Reject (Manuelle Freigabe mit Audit)

**Zweck:** Freigabe oder Ablehnung mit Pflichtkommentar und Audit-Trail

**Approve:**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --approve NOTICE-TEST-001 \
  --comment "Geprüft und freigegeben für Versand"
```

**Reject:**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --reject NOTICE-TEST-002 \
  --comment "Kunde bereits bezahlt, keine Mahnung nötig"
```

**VSCode Task:** `MVR: Approve (Tenant)`

**Audit-Trail:**
- Gespeichert in: `artifacts/reports/mahnwesen/<TENANT>/audit/`
- Format: `<NOTICE_ID>_<ACTION>_<TIMESTAMP>.json`
- Pflichtfelder: `tenant_id`, `notice_id`, `action`, `comment`, `user`, `timestamp`

---

### 3. Templates Validate

**Zweck:** Prüft, ob alle Templates (S1-S3) vorhanden und ladbar sind

**Befehl:**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --validate-templates \
  --verbose
```

**VSCode Task:** `MVR: Templates Validate`

**Output:**
```
TEMPLATE VALIDATION SUMMARY
Tenant: 00000000-0000-0000-0000-000000000001
✓ Stage 1: OK
  Path: agents/mahnwesen/templates/default/stage_1.jinja.txt
✓ Stage 2: OK
  Path: agents/mahnwesen/templates/default/stage_2.jinja.txt
✓ Stage 3: OK
  Path: agents/mahnwesen/templates/default/stage_3.jinja.txt
```

**Fehlerfall:**
- Template fehlt → **HARD FAIL** (kein Fallback)
- Exit-Code 1
- Keine Test-Templates erlaubt

---

### 4. Dry-Run (Simulation ohne Versand)

**Zweck:** Testet Prozess ohne echte Outbox-Events oder Brevo-Calls

**Befehl:**
```bash
MVR_DRY_RUN=true python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --limit 5 \
  --dry-run \
  --verbose
```

**VSCode Task:** `Mahnwesen: Dry-Run (Flock)`

**Erwartetes Resultat:**
- `success=true`
- `events_dispatched=0` (Dry-Run sendet keine Events)
- `notices_created > 0`

---

### 5. Live Send (Produktiv-Versand mit Rate-Limit)

**Zweck:** Sendet Mahnungen live via Brevo mit Rate-Limiting

**Befehl:**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --live \
  --rate-limit 2 \
  --verbose
```

**VSCode Task:** `MVR: Live Send (Test-Tenant, Rate-Limited)`

**Rate-Limit-Effekt:**
- `--rate-limit 2` → max. 2 Events/Run
- Rest wird geloggt und übersprungen

**Idempotenz:**
- Key: `(tenant_id|invoice_id|stage)`
- Duplicate → kein zweites Event

---

### 6. Kill-Switch (Notfall-Stop)

**Zweck:** Verhindert ALLE Versendungen (0 Events)

**Befehl:**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --kill-switch
```

**Output:**
```
⚠️  KILL SWITCH ACTIVE: No events will be sent
{
  "success": true,
  "kill_switch": true,
  "events_dispatched": 0,
  "message": "Kill switch prevented all sending"
}
```

**Exit-Code:** 0 (Success, aber 0 Events)

---

### 7. Daily KPIs (Täglich 07:30 CET)

**Zweck:** Aggregiert KPIs für alle Tenants und erzeugt JSON/MD-Reports

**Befehl:**
```bash
python tools/flock/playbook_mahnwesen.py \
  --report-daily \
  --verbose
```

**VSCode Task:** `MVR: Daily KPIs (All Tenants)`

**Output-Files:**
- `artifacts/reports/mahnwesen/<TENANT>/YYYY-MM-DD.json`
- `artifacts/reports/mahnwesen/<TENANT>/YYYY-MM-DD.md`

**KPI-Metriken:**
- `total_overdue`: Anzahl überfälliger Rechnungen
- `stage_1_count`, `stage_2_count`, `stage_3_count`
- `notices_ready`: Versandbereite Mahnungen
- `total_sent`: Tatsächlich versendet (0 in Dry-Run)
- `bounced`: Hard-Bounces (in Production)
- `escalations`: Stage 3 (Eskalationen)

---

## Troubleshooting (60-Sekunden-Quick-Fix)

### 1. Header 422 (Missing Tenant-ID)

**Symptom:**
```
API error 422: Missing required header: X-Tenant-Id
```

**Fix:**
```bash
# Prüfe, ob Tenant-ID korrekt ist
python tools/flock/playbook_mahnwesen.py --tenant <UUID> --dry-run
```

**Root Cause:** Tenant-ID nicht im korrekten UUID-Format

---

### 2. DB 500 (Database Error)

**Symptom:**
```
Read-API request failed: 500 Internal Server Error
```

**Fix:**
```bash
# 1. Prüfe DB-Verbindung
python tools/check_views.py

# 2. Prüfe Read-API Health
curl -H "X-Tenant-Id: <UUID>" http://localhost:8000/healthz

# 3. Falls Down → Backend neu starten
```

---

### 3. Template-NotFound

**Symptom:**
```
FileNotFoundError: Template 'stage_2.jinja.txt' not found
```

**Fix:**
```bash
# 1. Prüfe, ob Templates existieren
ls -la agents/mahnwesen/templates/default/

# 2. Validiere alle Templates
python tools/flock/playbook_mahnwesen.py \
  --tenant <UUID> --validate-templates

# 3. KEIN Fallback erlaubt → Template muss vorhanden sein
```

---

### 4. Bounce (Hard-Bounce)

**Symptom:**
```
Brevo API error: 400 - Invalid email address
```

**Fix:**
```bash
# 1. Prüfe Bounce-Liste (in Production)
# 2. Hard-Bounces werden NICHT erneut versendet
# 3. Kunde-Email in DB korrigieren
```

**Verhalten:**
- Hard-Bounce → automatisch übersprungen
- Kein erneuter Versuch

---

### 5. Rate-Limit Exceeded

**Symptom:**
```
Rate limit exceeded - skipping remaining notices
```

**Fix:**
```bash
# 1. Rate-Limit erhöhen (temporär)
python tools/flock/playbook_mahnwesen.py \
  --tenant <UUID> --rate-limit 100 --live

# 2. ODER: Mehrere Läufe mit kleineren Limits
```

---

## Canary-Deployment & Backout-Checkliste

### Canary (Schrittweise Freigabe)

**Phase 1: Smoke-Test (1 Tenant, 5 Notices)**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --live --rate-limit 5 --verbose
```

**Prüfung:**
- [ ] Alle 5 Notices versendet (events_dispatched=5)
- [ ] Brevo Message-IDs im Log
- [ ] Keine Exceptions
- [ ] Templates korrekt gerendert

---

**Phase 2: Extended-Test (1 Tenant, 25 Notices)**
```bash
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --live --rate-limit 25 --verbose
```

**Prüfung:**
- [ ] Rate-Limit respektiert (max. 25 Events)
- [ ] Idempotenz funktioniert (kein Duplicate)
- [ ] Bounces werden geloggt

---

**Phase 3: Full-Rollout (Alle Tenants)**
```bash
# Täglich via Cron (07:30 CET)
python tools/flock/playbook_mahnwesen.py \
  --report-daily
```

---

### Backout-Checkliste (Notfall-Rollback)

**Symptom:** Massen-Bounces, falsche Templates, Daten-Corruption

**Sofort-Maßnahmen:**
1. **Kill-Switch aktivieren:**
   ```bash
   python tools/flock/playbook_mahnwesen.py \
     --tenant <UUID> --kill-switch
   ```

2. **Outbox-Worker stoppen:**
   ```bash
   sudo systemctl stop 0admin-outbox-worker
   ```

3. **Audit-Log prüfen:**
   ```bash
   ls -la artifacts/reports/mahnwesen/<TENANT>/audit/
   ```

4. **Fehlerhafte Events in DLQ verschieben:**
   ```bash
   # Manuelle DB-Query (Production)
   UPDATE event_outbox SET status='dlq' WHERE tenant_id='<UUID>' AND created_at > NOW() - INTERVAL '1 hour';
   ```

5. **Templates auf Last-Known-Good zurücksetzen:**
   ```bash
   git checkout HEAD~1 -- agents/mahnwesen/templates/
   ```

---

## Monitoring & Alerting

### Metriken (Prometheus/OTEL)

- `mahnwesen_notices_created_total{tenant_id, stage}`
- `mahnwesen_events_dispatched_total{tenant_id, stage}`
- `mahnwesen_bounces_total{tenant_id, reason}`
- `mahnwesen_errors_total{tenant_id, error_type}`

### Log-Queries (JSON-Logs)

```bash
# Suche nach Fehlern
jq 'select(.level=="ERROR")' /var/log/0admin/mahnwesen.log

# Suche nach Tenant
jq 'select(.tenant_id=="<UUID>")' /var/log/0admin/mahnwesen.log

# Suche nach Brevo-Errors
jq 'select(.message | contains("Brevo API error"))' /var/log/0admin/mahnwesen.log
```

---

## Compliance & Audit

### Audit-Trail-Anforderungen

- **Wer:** User-ID aus `$USER` env var
- **Wann:** ISO-8601 Timestamp (UTC)
- **Was:** `action` (approve/reject)
- **Warum:** `comment` (Pflichtfeld)

### Retention

- Audit-Logs: **7 Jahre** (rechtliche Anforderung)
- Daily-KPIs: **2 Jahre**
- Brevo-Message-IDs: **1 Jahr**

---

## Anhang

### Template-Struktur

```
agents/mahnwesen/templates/
  <TENANT_ID>/
    stage_1.jinja.txt  # Freundliche Erinnerung
    stage_2.jinja.txt  # 7 Tage, weitere Maßnahmen
    stage_3.jinja.txt  # 7 Tage, rechtliche Schritte/Inkasso
  default/
    stage_1.jinja.txt
    stage_2.jinja.txt
    stage_3.jinja.txt
```

### Idempotenz-Key-Format

```
SHA-256(tenant_id|invoice_id|stage)
```

### Brevo-Fehler-Codes

- `201`: Success (Message sent)
- `400`: Invalid email/payload
- `401`: Invalid API key
- `402`: Credits exceeded
- `429`: Rate limit exceeded

---

**Ende des Runbooks**  
Bei Fragen: Siehe `docs/agents/mahnwesen.md`
