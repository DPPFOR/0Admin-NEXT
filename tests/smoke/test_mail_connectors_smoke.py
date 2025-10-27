from datetime import datetime, timedelta

from backend.apps.inbox.mail.connectors import (
    GraphConnector,
    ImapConnector,
    MailAttachment,
    MailMessage,
)


class DummyAttachment:
    def __init__(self, filename: str | None, mime: str, content: bytes):
        self.filename = filename
        self.mime = mime
        self.content = content
        self.size = len(content)


class DummyMessage:
    def __init__(self, ident: str, atts: list[MailAttachment]):
        self.id = ident
        self.received_at = datetime.utcnow()
        self.attachments = atts


class DummyImap(ImapConnector):
    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> list[MailMessage]:
        return [
            DummyMessage("m1", [DummyAttachment("a.pdf", "application/pdf", b"%PDF-1.4\n")]),
        ]


class DummyGraph(GraphConnector):
    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> list[MailMessage]:
        return [
            DummyMessage("g1", [DummyAttachment("b.png", "image/png", b"\x89PNG\r\n\x1a\n")]),
        ]


def test_interfaces_and_instantiation():
    imap = DummyImap()
    graph = DummyGraph()

    msgs_i = imap.fetch_messages("INBOX", datetime.utcnow() - timedelta(days=1), 10)
    msgs_g = graph.fetch_messages("INBOX", datetime.utcnow() - timedelta(days=1), 10)

    assert len(msgs_i) == 1 and msgs_i[0].attachments[0].mime == "application/pdf"
    assert len(msgs_g) == 1 and msgs_g[0].attachments[0].mime == "image/png"
