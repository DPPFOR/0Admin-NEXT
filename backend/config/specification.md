backend/config/specification.md
📘 Modul: Config (Konfiguration & Environment Management)
🎯 Zweck

config/ stellt zentrale Einstellungen und Laufzeitkonfiguration bereit, insbesondere für lokale, Entwicklungs- und Produktionsumgebungen.
Es ist der einzige Ort, an dem .env-Werte oder Umgebungsvariablen direkt verarbeitet werden.

🧩 Verantwortungsbereich
1) AppSettings (Pydantic Settings) → Laden/Validieren von .env
2) Kontext-Loader für Pfade, Ports, Feature-Toggles
3) Logger-Konfiguration (z. B. JSON-Logs, Rotation)
4) Konfigurationsprofile: local, test, prod
5) Validation & Overrides: Typprüfung, Default-Fallbacks

🧱 Struktur
backend/config/
├── settings.py
├── logging.py
├── profiles/
│   ├── local.env
│   ├── test.env
│   ├── prod.env
└── specification.md

⚙️ Laufzeitverhalten
- Beim Start: .env laden → Settings validieren → globale settings-Instanz bereitstellen
- Kein direktes Lesen von os.environ außerhalb config/
- Logging-Setup zentral (RotatingFileHandler, JSON-Format)

🧪 Tests
- Profile-switch zwischen local/test/prod simulieren
- Fehlende Variablen → definierte Exceptions
- Logging-Output validieren (keine Fehlkonfiguration)

📋 Definition of Done
- Alle Module können from config import settings verwenden
- Keine hardcodierten Secrets
- Konsistente Typprüfung & Fallback-Logik