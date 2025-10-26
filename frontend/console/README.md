# Mini-Console (Read-Only) v1

Zweck: Read-Only Betriebsübersicht für Health/Ready, Outbox/DLQ-Status, Tenants, Inbox/Parsed-Listen (PII-frei, mandantenbewusst).

Setup
- Node 20+, npm.
- ENV (Vite):
  - `VITE_API_BASE` — Basis-URL der bestehenden API (z. B. http://localhost:8000)
- Header-Policy (keine Tokens im LocalStorage):
  - Token & Tenant nur im Speicher setzen (z. B. zur Laufzeit via `window.__CONSOLE_CONFIG__ = { token: '...', tenant: '...' }`).

Entwicklung
- `npm install`
- `npm run dev`

Build/Tests
- `npm run build` → statische Files in `dist/`
- `npm test` → Vitest-UI-Tests (Mock-API)

Grenzen/PII
- Keine URIs/Filenames, keine E-Mail-Adressen in UI.
- Alle Requests senden `X-Trace-ID` (UUID v4 per Request).
- Siehe auch: ops/runbooks/console.md (Deployment/Proxy-Header).
