"""Mail connector interfaces (IMAP/Graph) — interfaces only.

This module defines Protocol-based interfaces for mail messages, attachments,
and connectors, plus nominal connector base classes for IMAP and Microsoft
Graph. Implementations must ensure TLS for IMAP, least-privilege scopes for
Graph, and must not leak PII (addresses/subjects/bodies) into logs.

No network access is performed here; this is interface and documentation only.
"""

from __future__ import annotations

import base64
import email
import imaplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode

import httpx

from backend.core.config import settings


@runtime_checkable
class MailAttachment(Protocol):
    """Attachment payload contract.

    Required fields:
    - filename: Optional original filename (do not log externally)
    - mime: Detected MIME type (e.g. application/pdf)
    - size: Size in bytes
    - content: Raw bytes of the attachment
    """

    filename: str | None
    mime: str
    size: int
    content: bytes


@runtime_checkable
class MailMessage(Protocol):
    """Mail message contract (metadata + attachments only).

    Required fields:
    - id: Provider message identifier (opaque)
    - received_at: Provider timestamp
    - attachments: List of MailAttachment objects
    """

    id: str
    received_at: datetime
    attachments: list[MailAttachment]


class MailConnector(Protocol):
    """Connector interface for listing messages with attachments.

    Implementations MUST:
    - Enforce TLS/SSL where applicable (IMAP)
    - Use least-privilege scopes (Graph)
    - Avoid logging PII (addresses, subjects, bodies)
    - Return only metadata + attachment bytes; no headers/body text
    - Perform paging/throttling per provider limits
    """

    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> list[MailMessage]:
        """Fetch up to 'limit' messages with attachments from 'mailbox' since the given time.

        Must return messages with attachment metadata and content bytes.
        Implementations must not perform network calls in tests and should be
        mockable/patchable for egress-free execution.
        """
        ...


class ImapConnector(MailConnector, ABC):
    """IMAP connector base class (interface only).

    Implementations must:
    - Require TLS (IMAP over SSL/TLS)
    - Authenticate with username/password or OAuth2 as configured
    - Select mailbox and iterate unseen/new messages as per policy
    - Robustly parse MIME parts to extract allowed attachments
    """

    @abstractmethod
    def fetch_messages(
        self, mailbox: str, since: datetime, limit: int
    ) -> list[MailMessage]:  # pragma: no cover - interface only
        raise NotImplementedError


class GraphConnector(MailConnector, ABC):
    """Microsoft Graph connector base class (interface only).

    Implementations must:
    - Use application/delegated auth with least-privilege scopes
    - List messages with attachments and download attachment bytes
    - Respect provider throttling and retry policies
    """

    @abstractmethod
    def fetch_messages(
        self, mailbox: str, since: datetime, limit: int
    ) -> list[MailMessage]:  # pragma: no cover - interface only
        raise NotImplementedError


__all__ = [
    "MailAttachment",
    "MailMessage",
    "MailConnector",
    "ImapConnector",
    "GraphConnector",
]


# Concrete implementations (prod-capable; network usage happens only when invoked)


@dataclass
class AttachmentImpl:
    filename: str | None
    mime: str
    size: int
    content: bytes


@dataclass
class MailMessageImpl:
    id: str
    received_at: datetime
    attachments: list[MailAttachment]


class ImapConnectorImpl(ImapConnector):
    """IMAP connector (TLS, LOGIN, SINCE, attachments only).

    Notes:
    - Uses IMAP4_SSL; no plaintext IMAP. Authentication with username/password.
    - Selects given mailbox; filters messages by INTERNALDATE >= since.
    - Parses MIME parts and yields non-inline attachments (Content-Disposition attachment).
    - PII: does not log subjects/addresses; only returns opaque message id and attachments bytes/metadata.
    - Network connections are created lazily in fetch_messages.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host or settings.IMAP_HOST
        self.port = port or settings.IMAP_PORT
        self.username = username or settings.IMAP_USERNAME
        self.password = password or settings.IMAP_PASSWORD

    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> list[MailMessage]:
        msgs: list[MailMessage] = []
        if not self.host or not self.username or not self.password:
            return msgs
        # Connect lazily; exceptions bubble up for caller to count as failure
        with imaplib.IMAP4_SSL(self.host, self.port) as M:
            M.login(self.username, self.password)
            M.select(mailbox or settings.MAILBOX_NAME, readonly=True)
            # SINCE uses DD-Mon-YYYY format (internaldate)
            since_str = since.strftime("%d-%b-%Y")
            typ, data = M.search(None, "SINCE", since_str)
            if typ != "OK":
                return msgs
            ids = data[0].split()[:limit]
            for num in ids:
                typ, resp = M.fetch(num, "(RFC822)")
                if typ != "OK":
                    continue
                raw = resp[0][1]
                em = email.message_from_bytes(raw)
                mid = em.get("Message-ID") or num.decode()
                # Received date fallback
                received = since
                atts: list[MailAttachment] = []
                for part in em.walk():
                    cd = (part.get("Content-Disposition") or "").lower()
                    if not cd or "attachment" not in cd:
                        continue
                    payload = part.get_payload(decode=True) or b""
                    mime = part.get_content_type() or "application/octet-stream"
                    fn = part.get_filename()
                    atts.append(
                        AttachmentImpl(filename=fn, mime=mime, size=len(payload), content=payload)
                    )
                if atts:
                    msgs.append(MailMessageImpl(id=mid, received_at=received, attachments=atts))
        return msgs


class GraphConnectorImpl(GraphConnector):
    """Microsoft Graph connector (App-only client credentials).

    - Lazily obtains OAuth2 token via client credentials.
    - Lists messages since a timestamp for a given user, top=limit.
    - For each message, loads attachments and yields fileAttachment items.
    - TLS verify on; redirects disabled; 429/5xx should be handled by caller policy/backoff.
    - No PII logging; only opaque ids and attachment bytes/metadata are returned.
    """

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id or settings.GRAPH_TENANT_ID
        self.client_id = client_id or settings.GRAPH_CLIENT_ID
        self.client_secret = client_secret or settings.GRAPH_CLIENT_SECRET
        self.user_id = user_id or settings.GRAPH_USER_ID

    def _get_token(self) -> str | None:
        if not (self.tenant_id and self.client_id and self.client_secret):
            return None
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        with httpx.Client(verify=True, follow_redirects=False, timeout=10.0) as c:
            r = c.post(url, data=data)
            if r.status_code != 200:
                return None
            return r.json().get("access_token")

    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> list[MailMessage]:
        out: list[MailMessage] = []
        token = self._get_token()
        if not token or not self.user_id:
            return out
        base = "https://graph.microsoft.com/v1.0"
        params = {
            "$filter": f"receivedDateTime ge {since.isoformat()}",
            "$top": str(limit),
            "$select": "id,receivedDateTime,hasAttachments",
        }
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(verify=True, follow_redirects=False, timeout=10.0, headers=headers) as c:
            r = c.get(f"{base}/users/{self.user_id}/messages?{urlencode(params)}")
            if r.status_code != 200:
                return out
            data = r.json()
            for m in data.get("value", [])[:limit]:
                if not m.get("hasAttachments"):
                    continue
                mid = m["id"]
                rr = c.get(
                    f"{base}/users/{self.user_id}/messages/{mid}/attachments?$select=id,name,contentType,contentBytes,@odata.type"
                )
                if rr.status_code != 200:
                    continue
                atts: list[MailAttachment] = []
                for a in rr.json().get("value", []):
                    if a.get("@odata.type") != "#microsoft.graph.fileAttachment":
                        continue
                    content_b64 = a.get("contentBytes") or ""
                    try:
                        content = base64.b64decode(content_b64)
                    except Exception:
                        content = b""
                    mime = a.get("contentType") or "application/octet-stream"
                    name = a.get("name")
                    atts.append(
                        AttachmentImpl(filename=name, mime=mime, size=len(content), content=content)
                    )
                if atts:
                    out.append(MailMessageImpl(id=mid, received_at=since, attachments=atts))
        return out


__all__ += [
    "AttachmentImpl",
    "MailMessageImpl",
    "ImapConnectorImpl",
    "GraphConnectorImpl",
]
