# docs/event_outbox_policy.md


- Event-Versionierung (schema_version-Pflicht)
  - Jedes Event trägt schema_version (SemVer: MAJOR.MINOR).
  - Producer-Pflicht: Version erhöhen bei breaking Changes; Non-breaking → MINOR.
  - Consumer-Pflicht: tolerant gegenüber unbekannten Feldern; Upcasting alter Versionen erlaubt.
  - Deprecation-Fenster: ≥ 2 MINOR-Versionen rückwärts kompatibel halten.
  - Registrierung: Schemas als JSON unter docs/events/schemas/<event_type>/<version>.json.
  - Akzeptanzkriterium: Neue Events ohne schema_version werden abgelehnt (Contract-Test).

- Retry-/Dead-Letter-Policy
  - Backoff-Stufen: 5 s → 30 s → 300 s, max. 3 Versuche pro Event.
  - Nach Überschreitung: Verschiebung nach DLQ mit reason, last_error, failed_at.
  - Idempotenz: Consumer persistiert (idempotency_key, event_type, tenant_id) vor Verarbeitung (UNIQUE).
  - Replay-Regel: Nur manuell nach Freigabe; vor Replay Ursache dokumentieren.
  - Metriken: publisher_lag, dlq_size, event_failures_total, retry_attempts_total.
  - Akzeptanzkriterium: Statusübergänge ausschließlich pending → processing → sent|failed|dlq.