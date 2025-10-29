# Sender DNS Checklist (Log-Only)

## Überblick

- Absenderadresse: `mahnungen@<tenant-domain>`
- Subdomain-Mailserver: `mail.<tenant-domain>`
- Diese Liste ist **log-only** – keine automatischen DNS-Änderungen.
- Alle Prüfungen erfolgen manuell via `dig`/`nslookup`. Ergebnisse werden im Repo als Erwartungswerte dokumentiert.

## Schritt-für-Schritt je Tenant

1. **SPF** (`<tenant-domain>`)
   - Erwartet: `v=spf1 include:spf.brevo.com -all`
   - Alternative Startkonfiguration: `~all`, später auf `-all` schärfen
2. **DKIM** (Brevo-Selector)
   - `brevo._domainkey.<tenant-domain> → CNAME brevo.domainkey.brevo.com`
   - `brevo2._domainkey.<tenant-domain> → CNAME brevo2.domainkey.brevo.com`
   - Brevo generiert finale Werte nach Domain-Verifikation
3. **DMARC**
   - `_dmarc.<tenant-domain> → v=DMARC1; p=none; rua=mailto:postmaster@<tenant-domain>`
   - Start mit `p=none` (Monitoring), später auf `quarantine`/`reject`
4. **MX**
   - `mail.<tenant-domain>` zeigt auf den autorisierten Mail-Relay (zu definieren)

### Manuelle Prüfkommandos

```
dig TXT <tenant-domain>
dig CNAME brevo._domainkey.<tenant-domain>
dig CNAME brevo2._domainkey.<tenant-domain>
dig TXT _dmarc.<tenant-domain>
```

Ergebnisse dokumentieren im jeweiligen Ops-Ticket und im Artefakt `sender_dns_status.json|.md`.

## Artefakte

- CLI: `python tools/operate/sender_dns_check.py --tenant <id> --domain <tenant-domain>`
- Output: `artifacts/reports/mahnwesen/<TENANT>/sender_dns_status.{json,md}` (Status `UNVERIFIED` bis Go-Live)

## Hinweise

- Keine automatischen DNS-Änderungen durchführen.
- Bei Domainwechsel: Checkliste aktualisieren und CLI erneut laufen lassen.
- Dokumentierte CNAME-Werte dürfen die Brevo-spezifischen Platzhalter enthalten, bis reale Werte vorliegen.

