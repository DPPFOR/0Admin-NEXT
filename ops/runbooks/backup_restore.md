# Backup & Restore (Postgres + file:// Storage)

## Backup-Plan (DB)
- Nightly `pg_dump` (Schema+Data) mit 7-Tage-Retention.
- Wöchentliches Vollbackup (Aufbewahrung 4 Wochen).
- Optional GPG-Verschlüsselung der Dumps.
- Platzhalter-Skripte (nur Dokumentation):
  - `ops/scripts/pg_backup.sh` – führt `pg_dump` aus, rotiert Altbestände, optional GPG.
  - `ops/scripts/pg_restore.sh` – stellt Wiederherstellung her (Staging/Test).

## Restore-Prozedur
1) Leere DB instanziieren; `alembic downgrade base` → `alembic upgrade head` (Baseline verified).
2) `pg_restore`/`psql` mit neuestem Dump einspielen.
3) `alembic current` prüfen (== `head`).
4) Konsistenz-Checks: Counts (`inbox_items`, `parsed_items`, `event_outbox`, `dead_letters`).
5) Metrik-Snapshot prüfen (Read/Ops API).

## Test-Restore (monatlich)
- In Staging ausführen; Checkliste:
  - Outbox/InBox Counts plausibel.
  - Read-APIs liefern Daten, Ops-API `outbox` Aggregation plausibel.
  - Publisher/Worker laufen (Dry-Run/isoliert), keine PII-Leaks.

## Orte/Namen
- Dumps: `/var/backups/0admin/postgres/` (rotierend).
- GPG-Keys: `/etc/0admin/keys/backup.gpg` (optional).
- Scripts (Platzhalter): `ops/scripts/pg_backup.sh`, `ops/scripts/pg_restore.sh`.

## GPG-Schlüssel & Rotation
- Schlüsselverwaltung: separater Ops-Prozess; Key-ID und Ablauf planen (jährlich), Test-Decrypt vor Rollout.
- Rotation: Parallelbetrieb alter/neuer Schlüssel (Dual-Key-Phase) bis alle Dumps mit neuem Schlüssel geschrieben werden.
- Notfall: Bei Schlüsselkompromittierung sofort Rotationsprozess starten; alte Dumps prüfen/isolieren.
