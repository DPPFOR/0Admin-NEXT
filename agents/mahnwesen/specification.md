agents/mahnwesen/specification.md
🎯 Zweck

Agenten zur ereignisgesteuerten Ausführung des Mahnwesens: Sammeln überfälliger Fälle, Stufenlogik, Dokumenterzeugung, Versand, Rückmeldungen.

🧩 Verantwortungsbereich
- Consume: invoice.overdue, payment.received, notice.created (Bestätigungspfad)
- Produce: notice.created, notice.sent, notice.failed, case.escalated
- Nebenbedingungen: Idempotenz per trace_id, Tenant-Isolation über Payload-Felder

🧱 Struktur
agents/mahnwesen/
├── workers/        # logic pro artefakt (collector, stage_calc, renderer, dispatcher)
├── schedules/      # cronartige triggers (täglich 06:00, stündlich 12:00, etc.)
├── adapters/       # mail (smtp/graph), calendar (ics), pdf (nur wrapper)
├── common/         # shared types, visibility, join/batch specs
└── specification.md

⚙️ Orchestrierung (Flock 0.5.3)
- Blackboard-Pattern; ausschließlich Typ-basierte Subscriptions
- Batching: optional für Versand (z. B. 25 Mahnungen/Batch)
- Join: Korrelation notice.created ↔ recipient policy binnen 24 h
- Visibility: Standard „public“, optional TenantVisibility(tenant_id) für SaaS

🔗 Schnittstellen (gegen Backend/Core)
- Input: Outbox-Events aus backend/products/mahnwesen und …/erechnung
- Output: Zustellbestätigungen zurück in Outbox (Statusfluss)
- Kein Direktimport von backend.* – nur über Artefakt-Schemen arbeiten

🧪 Tests
- Unit: Stufenlogik, Batch/Retry, Mail-Adapter-Fehlerpfade
- Integration: End-to-End „overdue→created→sent“, Idempotenz (trace_id)
- Observability: DuckDB-Traces aktivierbar, RED-Metriken pro Worker

✅ Definition of Done
- Wiederholbarer Lauf ohne Doppler (gleiche trace_id)
- Erfolgs-/Fehlerpfade publizieren konsistente Events
- Kein direkter DB-Zugriff; ausschließlich Blackboard + Outbox