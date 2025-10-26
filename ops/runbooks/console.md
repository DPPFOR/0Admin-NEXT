# Mini-Console (Read-Only) — Deployment

Ziel: Read-Only Betriebsübersicht für Health/Outbox/DLQ/Tenants/Inbox/Parsed, PII-frei.

Deployment
- Build: `cd frontend/console && npm ci && npm run build` → `dist/` bereitstellen (z. B. NGINX).
- Base-URL: `VITE_API_BASE` auf bestehende API zeigen.
- Header-Weiterleitung (Reverse Proxy): `Authorization`, `X-Tenant`, `X-Trace-ID` unverändert an Backend weiterreichen.
- Keine Tokens im LocalStorage speichern; Token/Tenant über `window.__CONSOLE_CONFIG__` (Memory) bereitstellen.

CORS/Proxy
- Konfigurieren, dass Browser-Anfragen mit den erforderlichen Headern an die API durchgelassen werden.

Grenzen/PII
- Keine URIs/Filenames/E-Mail-Adressen im DOM.
- Fehler-Toaster/Status-Banner enthält nur technische Hinweise (keine Payloads).
