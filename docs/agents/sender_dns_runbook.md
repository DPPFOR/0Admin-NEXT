# Sender & DNS Runbook — Mahnwesen Operate

## Zielbild

- Absender: `mahnungen@<tenant-domain>`
- Mail-Subdomain: `mail.<tenant-domain>`
- DNS-Schutz: SPF, DKIM (Brevo), DMARC (Monitoring → Enforcement)
- Bounce-Policy: Hard = sofort blocken, Soft = 3 Versuche / 72 h → Hard
- Security-Basics: Secrets via ENV, HTTPS-Transport, Log-Redaction aktiv, Retention definiert

## Schritte zur Freischaltung

1. **DNS vorbereiten** (Admin-Team)
   - SPF: `v=spf1 include:spf.brevo.com -all`
   - DKIM: `brevo._domainkey` & `brevo2._domainkey` als CNAME → Brevo-Targets
   - DMARC: `_dmarc` auf `v=DMARC1; p=none; rua=mailto:postmaster@<tenant-domain>`
   - MX: `mail.<tenant-domain>` → autorisierter Relay
   - Dokumentation in `sender_dns_status.json|.md` (log-only)
2. **Bounce & Blocklist prüfen**
   - Hard Bounce → sofortige Blockade (`tools/operate/bounce_reconcile.py`)
   - Soft Bounce → `max_attempts=3` in 72 h, danach Promotion → Blocklist
   - Artefakte: `blocklist.json`, `bounce_reconcile_<ts>.json`, `sender_policy_probe.json`
3. **Security & Compliance**
   - Secrets ausschließlich via ENV (`BREVO_*`, keine Klartext-Configs)
   - Transport: Brevo API (HTTPS), SPF/DKIM/DMARC per DNS dokumentiert
   - Redaction: `tools/operate/redaction_probe.py` → `artifacts/tests/redaction_probe.json`
   - Retention: Inbox 90 d, Logs 30 d, Audit 365 d (siehe Doku)
4. **Go/No-Go-Checkliste**
   - ✅ DNS-Einträge stimmen (manuell geprüft)
   - ✅ Bounce-Policy aktiv, Blockliste leer bzw. dokumentiert
   - ✅ Sender Policy Probe zeigt alle ENV=SET
   - ✅ Redaction-Probe maskiert PII
   - ❌ => Rollout stoppen & Incident eröffnen

## Operative Tools

- `python tools/operate/sender_dns_check.py --tenant <id> --domain <tenant-domain>`
  - erstellt Erwartungswerte (`sender_dns_status.*`)
- `python tools/operate/sender_policy_probe.py --tenant <id>`
  - prüft ENV & Bounce-Policy
- `python tools/operate/redaction_probe.py`
  - validiert Maskierungslogik (`redaction_probe.json`)

## Security-Kurzcheck

- Secrets via `.env` / Secret-Store → niemals im Repo
- Brevo-Kommunikation über HTTPS; keine unsicheren Protokolle
- Log-Redaction deckt E-Mail, IBAN, Telefon (siehe Probe)
- Retention: Inbox 90 d, Blocklist & KPI 90 d, Audit 365 d, Logs 30 d

## Eskalation & Support

- DNS-Abweichung → Ticket an Infrastruktur-Team (keine Auto-Korrektur)
- Bounce-Anstieg → `bounce_reconcile` analysieren, Sender ggf. blockieren
- Redaction-Fehler → Logging-Filter priorisiert fixen vor Go-Live
- Dokumentation fortlaufend pflegen (`sender_dns_checklist.md`, Artefakte, Ops-Log)

