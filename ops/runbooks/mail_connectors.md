# Mail-Connector Interfaces (IMAP/Graph)

Ziel: klare Schnittstellen für Mail-Fetch ohne Implementierungsdetails, mit Fokus auf Sicherheit/Compliance.

Sicherheit/Compliance
- IMAP: TLS/SSL verpflichtend; keine Plain-IMAP. Zertifikatsprüfung aktiv.
- Graph: Least-Privilege Scopes (nur Lesen von Nachrichten/Attachments); keine Token/Headers in Logs.
- PII: Keine Adressen, Namen, Betreffzeilen oder Body-Snippets in Logs/Events. Erlaubt: `message_id` (opaque), `mailbox` (Technik-Name), MIME, Größen, Hashes, Zeitstempel.
- Limits/Throttling: Provider-Limits beachten; Backoff/Retry pro Connector-Policy.

Interfaces
- `MailAttachment` (Protocol): `filename?: str`, `mime: str`, `size: int`, `content: bytes`
- `MailMessage` (Protocol): `id: str`, `received_at: datetime`, `attachments: List[MailAttachment]`
- `MailConnector` (Protocol): `fetch_messages(mailbox: str, since: datetime, limit: int) -> List[MailMessage]`
- `ImapConnector(MailConnector)`: abstrakte Basisklasse; TLS erzwingen; MIME-Parts robust parsen.
- `GraphConnector(MailConnector)`: abstrakte Basisklasse; Scopes minimal; Attachments laden.

Hinweise für Implementierer
- Kein Netz in Tests: Implementierungen mit klaren Extension Points versehen; in Smokes egress-frei via Mocks verwenden.
- MIME/Größenvalidierung im Inbox-Flow; Connectoren liefern Bytes und Metadaten, keine Business-Entscheidungen.
- Logging: nur technisch notwendige IDs (message_id, mailbox), keine PII.
 
Produktionsbetrieb
- IMAP: TLS/SSL erzwingen; Login per USER/PASS. LIMIT via `MAIL_BATCH_LIMIT` (z. B. 25), SINCE-Zeitfenster via `MAIL_SINCE_HOURS`.
- Graph (App-only): OAuth2 Client-Credentials; Messages-Filter `receivedDateTime ge ...`, Attachments via `/attachments` (nur `#microsoft.graph.fileAttachment`).
- Throttling/Backoff: `MAIL_MAX_BYTES_PER_RUN`, `MAIL_RETRY_MAX`, `MAIL_BACKOFF_STEPS` (ms) — im V1 durch Connector-Policy beachten; Upstream `process_mailbox` erzwingt Byte-Cap.
- Alerting: `mail_deferred_total` Δ > 100 pro 15 Minuten → Warnung (Hinweis auf nachhaltige Drosselung/zu kleine Caps).
- Fehler-Matrix: Auth (fail-fast), Netzwerk (retryable), Attachment-Decode (non-retryable, zählt als Failure), 429/5xx (Backoff beachten, `Retry-After`).
- PII-Policy: Keine Adressen/Subjects in Logs/Events; nur `mailbox`, `message_id` (opaque), MIME, Größen, Hashes.

Dependency Injection (DI)
- Der Ingest-Pfad akzeptiert einen `MailConnector` via Parameter: `process_mailbox(tenant_id, mailbox, connector)`.
- Wenn kein Connector übergeben wird, nutzt die Pipeline eine ENV-basierte Default-Factory (imap|graph) und bleibt egress-frei.
- Beispiel (Test-Mock):
  ```python
  class DummyConnector(ImapConnector):
      def fetch_messages(self, mailbox, since, limit):
          return [MailMessage(id='m1', received_at=datetime.utcnow(), attachments=[...])]

  process_mailbox(tenant_id, 'INBOX', connector=DummyConnector())
  ```
