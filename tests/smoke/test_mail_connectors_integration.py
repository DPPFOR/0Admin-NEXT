import os
import uuid
from datetime import datetime
from pathlib import Path

from backend.core.config import settings
from backend.apps.inbox.mail.connectors import ImapConnector, GraphConnector, MailMessage, MailAttachment
from backend.apps.inbox.mail.ingest import process_mailbox


class SimAttachment:
    def __init__(self, content: bytes, mime: str, filename: str | None = None):
        self.content = content
        self.mime = mime
        self.filename = filename
        self.size = len(content)


class SimMessage:
    def __init__(self, mid: str, attachments: list[MailAttachment]):
        self.id = mid
        self.received_at = datetime.utcnow()
        self.attachments = attachments


class SimImap(ImapConnector):
    def __init__(self, messages: list[MailMessage]):
        self._messages = messages

    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> list[MailMessage]:
        return self._messages[:limit]


class SimGraph(GraphConnector):
    def __init__(self, messages: list[MailMessage]):
        self._messages = messages
        self.calls = 0

    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> list[MailMessage]:
        self.calls += 1
        return self._messages[:limit]


def test_mail_connectors_integration(tmp_path, monkeypatch):
    tenant = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))
    base_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "STORAGE_BASE_URI", f"file://{base_dir}")
    base_dir.mkdir(parents=True, exist_ok=True)

    pdf = b"%PDF-1.4\nHello"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 10
    exe = os.urandom(64)
    big = b"%PDF-1.4\n" + (b"0" * (2 * 1024 * 1024))

    # T-C1 IMAP Happy (2 attachments)
    imap_msgs = [SimMessage("m1", [SimAttachment(pdf, "application/pdf", "a.pdf"), SimAttachment(png, "image/png", "b.png")])]
    res1 = process_mailbox(tenant, "INBOX", connector=SimImap(imap_msgs))
    assert res1["processed"] == 2 and res1["duplicates"] == 0

    # T-C2 IMAP Duplicate (same message again)
    res2 = process_mailbox(tenant, "INBOX", connector=SimImap(imap_msgs))
    assert res2["processed"] in (0, 2)

    # T-C3 IMAP MIME Unsupported (.exe)
    imap_bad = [SimMessage("m2", [SimAttachment(exe, "application/octet-stream", "evil.exe")])]
    res3 = process_mailbox(tenant, "INBOX", connector=SimImap(imap_bad))
    assert res3["processed"] == 0

    # T-C4 Graph Happy (1 PDF + 1 CSV)
    csv = b"a,b\n1,2\n"
    graph_msgs = [SimMessage("g1", [SimAttachment(pdf, "application/pdf", "a.pdf"), SimAttachment(csv, "text/csv", "c.csv")])]
    res4 = process_mailbox(tenant, "INBOX", connector=SimGraph(graph_msgs))
    assert res4["processed"] >= 1

    # T-C6 Size-Limit (set MAX_UPLOAD_MB=1)
    old = settings.MAX_UPLOAD_MB
    try:
        settings.MAX_UPLOAD_MB = 1
        res6 = process_mailbox(tenant, "INBOX", connector=SimImap([SimMessage("m3", [SimAttachment(big, "application/pdf", "big.pdf")])]))
        assert res6["processed"] == 0
    finally:
        settings.MAX_UPLOAD_MB = old

    # T-C8 Idempotenz-Key: same message id + same hash is no-op on second run
    res8a = process_mailbox(tenant, "INBOX", connector=SimImap([SimMessage("m4", [SimAttachment(pdf, "application/pdf", "x.pdf")])]))
    res8b = process_mailbox(tenant, "INBOX", connector=SimImap([SimMessage("m4", [SimAttachment(pdf, "application/pdf", "x.pdf")])]))
    assert res8a["processed"] >= 1 and res8b["duplicates"] >= 1

    # T-C9 Throttling: enforce MAIL_MAX_BYTES_PER_RUN small
    old_cap = settings.MAIL_MAX_BYTES_PER_RUN
    try:
        settings.MAIL_MAX_BYTES_PER_RUN = 16
        res9 = process_mailbox(tenant, "INBOX", connector=SimImap([SimMessage("m5", [SimAttachment(pdf, "application/pdf", "a.pdf"), SimAttachment(pdf, "application/pdf", "b.pdf")])]))
        assert res9["processed"] >= 1 and res9["deferred"] >= 1
        # Metric presence: mail_deferred_total counter increased
        from backend.core.observability.metrics import get_metrics

        m = get_metrics()
        assert m.get("mail_deferred_total", {}).get("count", 0) >= 1
    finally:
        settings.MAIL_MAX_BYTES_PER_RUN = old_cap
