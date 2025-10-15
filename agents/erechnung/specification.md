agents/erechnung/specification.md
🎯 Zweck

Agenten für Erstellung, Validierung und Versand elektronischer Rechnungen (XRechnung/ZUGFeRD) inkl. Rückmeldungen & Fehlerbehandlung.

🧩 Verantwortungsbereich
- Consume: einvoice.issued (→ Versand), einvoice.failed (→ Retry/Alarm), optional payment.received
- Produce: einvoice.sent, einvoice.delivery_failed, einvoice.corrected.requested
- Nebenbedingungen: Profilabhängige Kanäle (Mail/PEPPOL/Upload), Hash-stabile Artefakte

🧱 Struktur
agents/erechnung/
├── workers/        # issuer_bridge, validator_bridge, sender_mail, sender_peppol
├── validators/     # schema/profile checks (nur wrappers, kein business code)
├── adapters/       # pdf/xml storage, transport (smtp/peppol/api)
├── common/         # types, batch/join specs, visibility
└── specification.md

⚙️ Orchestrierung (Flock 0.5.3)
- AND-Gate: Versand wartet auf issued und erfolgreiches validate
- BatchSpec: Versand in Paketen (Kosten & Rate-Limit)
- Retry-Policy: exponentiell mit Max-Attempts; delivery_failed Event bei Exhaustion

🔗 Schnittstellen (gegen Backend/Core)
- Input: einvoice.issued inkl. Pfade zu XML/PDF (vom Backend erzeugt)
- Output: einvoice.sent/delivery_failed mit Kanal/Empfänger/Diagnostic
- Storage nur über Adapter (keine Pfadlogik im Worker)

🧪 Tests
- Unit: Profilrouting, Kanalwahl, Retry/Circuit-Breaker
- Integration: Issue→Validate→Send (mit Mocks), Idempotenz (trace_id)

Deterministik: gleiche Inputs → identische Versandpayloads (Hash-Vergleich)

✅ Definition of Done
- Erfolgreiche Zustellung je Profil/Kanal nachweisbar (Artefakte unter artifacts/)
- Fehlerläufe erzeugen delivery_failed mit Gründen & Remediation-Hinweisen
- Strikte Entkopplung: keine Backend-Imports, nur Artefakt-Verträge