# backend/
Zentrale Geschäftslogik und Core-Services von 0Admin

## 🎯 Zweck
Das Backend stellt die fachliche Logik und die Querschnittsdienste bereit. 
Es trennt **apps (Fach)** von **core/common/config/migrations (Technik/Querschnitt)** und bleibt vollständig entkoppelt von UI und Agents.

## 🧭 Leitprinzipien
- README nur hier auf Root-Ebene. Alle Unterordner dokumentieren sich über **specification.md**.
- Strikte Importregeln: Apps → (core|common), niemals Apps ↔ Apps.
- pip-only, Python 3.12. Backend ist agenten- und UI-neutral.

## 🧱 Strukturüberblick
backend/
├── apps/ → Fachmodule (z. B. mahnwesen, erechnung)
│ ├── mahnwesen/
│ │ └── specification.md
│ └── erechnung/
│ └── specification.md
│
├── core/ → Querschnittskomponenten (eventstore, outbox, documents, numbering, holidays, auth)
│ └── specification.md
│
├── common/ → Shared Utilities, Basisklassen, Konstanten
│ └── specification.md
│
├── config/ → Settings, Logging, Profile
│ └── specification.md
│
├── migrations/ → Alembic-Konfiguration & Revisionen
│ └── specification.md
└── README.md → (dieses Dokument)

bash
Code kopieren

## 🔗 Navigation (Spezifikationen)
- Apps
  - [apps/mahnwesen/specification.md](apps/mahnwesen/specification.md)
  - [apps/erechnung/specification.md](apps/erechnung/specification.md)
- Querschnitt
  - [core/specification.md](core/specification.md)
  - [common/specification.md](common/specification.md)
  - [config/specification.md](config/specification.md)
  - [migrations/specification.md](migrations/specification.md)

## 🧪 Tests (Meta)
- Integrationstests je App liegen unter `tests/integration/<app>`.
- E2E-Tests systemweit unter `tests/e2e/`.
- Policy: `pytest -W error`, deterministisch, keine externen Seiteneffekte.
2) backend/common/specification.md
(bereitgestellt; hier nochmal final zum Einfügen)

markdown
Code kopieren
# backend/common/specification.md
## 📘 Modul: Common (Utilities & Shared Models)

### 🎯 Zweck
`common/` bündelt gemeinsam genutzte Hilfsfunktionen, Basisklassen, Schemas und Konstanten, die nicht domänenspezifisch sind.

### 🧩 Verantwortungsbereich
1. Helper-Funktionen (Datumsformatierung, Logging, Hashing)
2. Enums/Konstanten (Status, Fehlercodes, Currency-Codes)
3. BaseModel-Erweiterungen (Pydantic) mit `trace_id`, `tenant_id`, `created_at`
4. Exceptions mit standardisiertem Aufbau (`error_code`, `detail`, `context`)
5. Utility-Klassen (z. B. SafeDecimal, Timer, RetryPolicy)

### 🧱 Struktur
backend/common/
├── helpers/
├── models/
├── constants/
├── exceptions/
└── specification.md

markdown
Code kopieren

### 🧪 Tests
- Deterministische Unit-Tests, keine Abhängigkeit zu Apps/Core.

### 📋 Definition of Done
- Importierbar aus Apps und Core, keine Seiteneffekte, Tests grün.
3) backend/config/specification.md
markdown
Code kopieren
# backend/config/specification.md
## 📘 Modul: Config (Konfiguration & Environment Management)

### 🎯 Zweck
Zentrale Settings- und Laufzeitkonfiguration. Einziger Ort, der `.env`/Umgebungsvariablen direkt liest/validiert.

### 🧩 Verantwortungsbereich
1. AppSettings (Pydantic Settings)
2. Kontext-Loader (Pfade, Ports, Feature-Toggles)
3. Logger-Konfiguration (JSON-Logs, Rotation)
4. Profile: `local`, `test`, `prod`
5. Validation & Overrides (Typprüfung, Defaults)

### 🧱 Struktur
backend/config/
├── settings.py
├── logging.py
├── profiles/
│ ├── local.env
│ ├── test.env
│ ├── prod.env
└── specification.md

markdown
Code kopieren

### ⚙️ Laufzeitverhalten
- `.env` laden → validieren → globale `settings`-Instanz bereitstellen.
- Kein direktes `os.environ` außerhalb `config/`. Logging zentral.

### 🧪 Tests
- Profile-Switch simulieren; fehlende Variablen → definierte Exceptions.

### 📋 Definition of Done
- `from backend.config import settings` überall nutzbar; keine Secrets im Code.
4) backend/migrations/specification.md
markdown
Code kopieren
# backend/migrations/specification.md
## 📘 Modul: Migrations (Alembic Lifecycle)

### 🎯 Zweck
Verwaltet Datenbankschemata, Revisionen und Migrationsläufe via Alembic-Only-Policy; reproduzierbar und reversibel.

### 🧩 Verantwortungsbereich
1. Alembic-Konfiguration (`alembic.ini`, `env.py`)
2. Revisionsverwaltung (`versions/*.py`)
3. Lifecycle (`upgrade`, `downgrade`, `stamp`)
4. Dokumentation der Abhängigkeiten
5. CI-Integration

### 🧱 Struktur
backend/migrations/
├── alembic.ini
├── env.py
├── versions/
│ ├── 20241015_0001_init.py
│ └── ...
└── specification.md

markdown
Code kopieren

### ⚙️ Richtlinien
- Migrationen nur via Alembic; jede Revision downgradefähig; CI prüft Up/Down.

### 🧪 Tests
- Roundtrip `upgrade → downgrade → upgrade`; Schema-Diff protokolliert.

### 📋 Definition of Done
- Up-/Down-Läufe grün, keine Raw-SQL-Shortcuts, Artefakte vorhanden.