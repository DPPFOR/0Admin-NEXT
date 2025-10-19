# Logrotation (JSON-Logs)

Ziel: kontrollierte Größe/Retention der JSON-Logs; PII-sicher (keine Payloads/Dateinamen).

Vorgaben
- journald: Systemd-Unit loggt nach stdout; Rotation via journald-Policies (`SystemMaxUse`, `MaxRetentionSec`).
- Datei-Logs (optional): Logrotate einsetzen mit max Größe, `rotate N`, `compress`.

Platzhalter-Konfig (Beispiel)
- Datei: `ops/scripts/logrotate.conf` (nur Textbeispiel, keine aktive Nutzung im Repo)
  ```
  /var/log/0admin/*.log {
      daily
      rotate 14
      size 50M
      compress
      delaycompress
      missingok
      notifempty
      copytruncate
  }
  ```

Hinweise
- Keine Rohpayloads/Dateinamen in Logs ausgeben.
- Sensitive Header (Tokens) nie loggen; nur gehashte oder Opaque-IDs.
