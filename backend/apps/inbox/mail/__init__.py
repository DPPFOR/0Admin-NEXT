"""Mail ingest (IMAP/Graph) to Inbox flow.

Connectors are minimal and intended to be monkeypatched in tests; the ingest
pipeline reuses storage, dedupe, and outbox emission from the inbox app.
"""
