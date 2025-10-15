# artifacts/
Zentrale Sammelstelle für Lauf-, Test- und Nachweis-Artefakte. Keine Business-Logik, kein Code.

## 🎯 Zweck
- Einheitlicher Ort für alle generierten Ausgaben (Logs, Reports, Proofs).
- Verhindert Wildwuchs in Backend/Agents/Root.
- Grundlage für CI-Auswertung und Audits.

## 🧱 Struktur
artifacts/
├── env/ # Python/pip/Tool-Versionen, Systeminfos (install.txt, versions.txt)
├── run/ # Befehlsprotokolle, Exit-Codes, stdout/stderr, trace_*.csv
├── tests/ # Pytest-Reports, Coverage, junit.xml
├── migrations/ # Alembic: current/history, upgrade/downgrade-Protokolle
├── reports/ # Dauerhafte Ergebnisdateien (CSV/JSON/PDF) mit Nachweischarakter
├── outbox/ # Prüf-/Exportartefakte aus Outbox-Läufen (Mock/Preview)
├── inbox/ # Import-/Parse-Proben (Mock/Preview)
├── monitoring/ # Schwellen-/Alert-Auswertungen, Tagesreports
└── .tmp/ # Temporär während Runs/Tests (muss nach Run geleert werden)

markdown
Code kopieren

## 📜 Namensschema
`<bereich>/<YYYY-MM-DD>/<HHMMSS>_<kurzname>.<ext>`  
Beispiel: `run/2025-10-15/143210_e2e_mahnwesen.log`

## 🔐 Policies
- **Ablagepflicht:** Alle Lauf-/Test-/Nachweisdateien gehören hierher, sonst nirgends.
- **Temp-Regel:** Kurzlebiges nur unter `artifacts/.tmp/` → nach erfolgreichem Run löschen.
- **pip-only:** Keine Toolchain-Artefakte aus `uv/poetry/pipenv`.
- **Keine Businessdaten:** Keine produktiven Kundendaten ablegen.

## 🧪 CI & Auswertung
- CI sammelt Inhalte aus `env/`, `tests/`, `migrations/`, `reports/`.
- Fails/Warnungen werden als Dateien unter `run/` oder `tests/` persistiert.
- Alembic-Validierung schreibt nach `migrations/` (current/history/roundtrip).

## 🧹 Cleanup (Agent/Tests)
- Nach jedem erfolgreichen Run: `artifacts/.tmp/` rekursiv leeren.
- Dauerhafte Nachweise (Reports, finals, coverage) bleiben erhalten.

## ✅ Definition of Done
- Relevante Artefakte pro Run vorhanden und nachvollziehbar benannt.
- Keine Artefakte außerhalb von `artifacts/**`.
- `artifacts/.tmp/` ist nach Erfolg leer (oder existiert nur als Ordner).