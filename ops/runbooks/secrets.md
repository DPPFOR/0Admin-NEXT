# Secrets & Rotation (Dual-Key)

Ziel: Geheimnisse sicher verwalten (ENV-only) und ohne Downtime rotieren. Dual-Key-Verfahren (active/previous) für HMAC-Schlüssel (z. B. Cursor-/Audit-Hashing).

Begriffe
- Active Key: `CURSOR_HMAC_KEY` (wird für neue Signaturen/Hashes verwendet)
- Previous Key: `CURSOR_HMAC_KEY_PREVIOUS` (akzeptiert/verifiziert Alt-Signaturen während des Umschaltfensters)
- Rotationsfenster: 90 Tage (siehe `TOKEN_ROTATION_WINDOW_DAYS`)

Voraussetzungen
- Secrets ausschließlich via Umgebungsvariablen (GitHub Secrets/Server-Env).
- Keine Klartext-Secrets in Logs/Artefakten. Maskierung aktiv halten.

Ablauf (Dual-Key Rotation)
1) Vorbereitung
   - Generiere neuen starken Secret-Wert (>= 32 Bytes) für `CURSOR_HMAC_KEY`.
   - Setze `CURSOR_HMAC_KEY_PREVIOUS` = aktueller (alter) `CURSOR_HMAC_KEY`.
   - Setze `CURSOR_HMAC_KEY` = NEUER Key.
   - Setze/prüfe `TOKEN_ROTATION_WINDOW_DAYS=90`.
2) Rollout
   - Deploy/Restart aller Services (App, Worker, Publisher), damit ENV aktiv wird.
   - Während des Fensters werden neue Signaturen/Hashes mit dem NEUEN Key erzeugt; Alt-Signaturen werden anhand `CURSOR_HMAC_KEY_PREVIOUS` akzeptiert.
3) Überwachung
   - Prüfe Logs/Metriken (keine PII/Secrets):
     - Read-API: Keyset-Cursor funktionieren vor/nach Rotation (Test-Paging mit vorher ausgegebenen Cursor-Werten).
     - Ops-API: `actor_token_hash` stabil (Hash-Funktionswechsel vermeiden; HMAC-Schlüsselwechsel ist erwartbar → alte und neue Hashes koexistieren im Fenster).
4) Abschluss
   - Nach Ablauf des Fensters (90 Tage) `CURSOR_HMAC_KEY_PREVIOUS` entfernen/leeren.
   - Deploy/Restart durchführen.

Rollback
- Falls Probleme auftreten:
  - Setze `CURSOR_HMAC_KEY` zurück auf den vorherigen Key (der noch in `CURSOR_HMAC_KEY_PREVIOUS` steht).
  - Setze `CURSOR_HMAC_KEY_PREVIOUS` leer.
  - Deploy/Restart.
  - Nach erfolgreicher Stabilisierung neuen Rotationszyklus neu planen.

Prüfkommandos (operativ)
- ENV prüfen:
  - `printenv CURSOR_HMAC_KEY | wc -c` (Länge >= 32)
  - `printenv CURSOR_HMAC_KEY_PREVIOUS | wc -c` (gesetzt im Fenster)
- Read-API Cursor (Keyset):
  - Vor Rotation Cursor holen: `GET /api/v1/inbox/items?limit=5` → `next` merken.
  - Nach Rotation: `GET /api/v1/inbox/items?cursor=<next>` → 200 OK; `invalid_cursor` würde auf fehlerhafte Akzeptanz hindeuten.
- Ops-Logs (Auszug, per Journal/grep):
  - `actor_token_hash` vorhanden; kein Klartext-Token.

Reminder/Prozess
- Rotation quartalsweise planen. 14 Tage vor Ablauf Reminder/Ticket eröffnen (Ops-Board).
- Nach Abschluss: Dokumentation aktualisieren (Secrets-Rotation-Datum), nächsten Termin setzen.

Hinweise
- Niemals Klartext-Secrets loggen.
- Admin-/Service-Tokens getrennt verwalten (`ADMIN_TOKENS`, `AUTH_SERVICE_TOKENS`).
- Für Webhook-Ziele ggf. Domain-Allowlist (`WEBHOOK_DOMAIN_ALLOWLIST`) pflegen.
