backend/common/specification.md
📘 Modul: Common (Utilities & Shared Models)
🎯 Zweck

common/ bündelt gemeinsam genutzte Hilfsfunktionen, Basisklassen, Schemas und Konstanten, die nicht domänenspezifisch sind.
Es dient als Werkzeugkasten für alle Apps und Core-Komponenten.

🧩 Verantwortungsbereich
1) Gemeinsame Helper-Funktionen (z. B. Datumsformatierung, Logging, Hashing)
2) Enums/Konstanten für Status, Fehlercodes, Currency-Codes usw.
3) BaseModel-Erweiterungen (Pydantic) mit Standardfeldern wie trace_id, tenant_id, created_at
4) Exceptions mit standardisierter Struktur (error_code, detail, context)
5) Utility-Klassen (z. B. DictHelper, SafeDecimal, Timer, RetryPolicy)

🧱 Struktur
backend/common/
├── helpers/
├── models/
├── constants/
├── exceptions/
└── specification.md

🧪 Tests
- Alle Helper und Models deterministisch testbar
- Keine Abhängigkeit zu Core- oder App-Modulen
- 100 % pip-kompatibel, Python 3.12

📋 Definition of Done
- Alle Basisklassen und Konstanten werden von anderen Modulen importierbar
- Keine Seiteneffekte, keine IO-Operationen
- Tests vollständig grün, deterministisch