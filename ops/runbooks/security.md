# Security & Data Protection (v1)

Ziele: Geheimnisse schützen, PII minimieren, Admin-Only Operations, Auditierbarkeit, Token-Rotation.

Secrets/ENV
- Secrets ausschließlich via Umgebungsvariablen/Secret-Store (GitHub Secrets, Server-Env). Keine Secrets in Artefakten/Logs.
- `CURSOR_HMAC_KEY` (≥32 Bytes) ist Pflicht in Produktion; Rotation quartalsweise, Dual-Key-Phase möglich (active/previous) – Rollout dokumentieren.
- `ADMIN_TOKENS` (CSV) getrennt von `AUTH_SERVICE_TOKENS` (Service-Rolle).

Tokens & Audit
- Ops-APIs nur mit `ADMIN_TOKENS` zugänglich.
- Audit-Logs enthalten gehashte `actor_token_id` (`hash_actor_token` via HMAC); niemals Klartext-Token.
- Alle API-Calls sollen `X-Trace-ID` tragen (Server generiert falls fehlt).

PII-Minimierung
- Keine Dateinamen, E-Mail-Adressen oder Raw-Bodies in Logs/Events/Responses.
- Read-APIs liefern Whitelists; keine URIs/Dateipfade ausgeben.

Publisher/Webhook
- HTTPS only; TLS verify, keine Redirects.
- Header-Allowlist strikt; verbotene Header (`Authorization`, `Cookie`, `Set-Cookie`) werden nicht gesendet.
- Optionale Domain-Allowlist `WEBHOOK_DOMAIN_ALLOWLIST` (host-suffix basiert) für Ziel-Webhook.

Ops-APIs (DLQ/Replay)
- `dry_run=true` default; Commit nur mit Admin-Token; Idempotenz bleibt aktiv.
- Replay-Audit: Logs enthalten `actor_token_hash`, `trace_id`, Anzahl, Zeitstempel (PII-frei).

Backups
- `pg_dump` Dumps GPG-verschlüsseln (empfohlen); Schlüsselverwaltung dokumentieren (Rotation inkl. Test-Decrypt).
- Dump-Logs dürfen keine DSN/Passwörter enthalten.

CI-Security
- `gitleaks` als Secret-Scan; `pip-audit` erstellt SBOM/Report. Nightly kann bei High/Critical failen (Policy).
