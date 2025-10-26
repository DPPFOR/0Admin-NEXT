# Storage-Rotation (file://)

Ziel: Content-addressed Dateien unter `STORAGE_BASE_URI` rotieren/quotieren, ohne PII zu leaken.

Regeln (Vorschlag)
- Kandidaten: `received_at > 180 d` AND `status in (parsed, error)` AND kein aktiver Case/Workflow referenziert die Datei.
- Mindestsatz behalten: letzte `N` je Tenant (konfigurierbar).
- Report-First: zunächst trockener Lauf (Liste, Gesamtgröße, Alter), danach Commit-Lauf.

Platzhalter-Skript
- `ops/scripts/storage_rotate.sh` – erzeugt Dry-Run-Report und optional Commit; berücksichtigt `STORAGE_BASE_URI`-Layout (`file:///<base>/<tenant>/<HH>/<sha>.<ext>`).
- Logs: ausschließlich Hash/URI-Prefix loggen; keine Dateinamen/PII.

Quotas/Alarme
- Quoten je Filesystem/Partition definieren; bei >80 % Nutzung Warnung, >90 % Alarm (Minimal-Checker liest `df`-Werte und erzeugt JSON-Report/Exit-Codes).
