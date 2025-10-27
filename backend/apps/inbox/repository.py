from dataclasses import dataclass

from sqlalchemy import Column, DateTime, String, Table, Text, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.sql import func


@dataclass
class InboxItem:
    id: str
    tenant_id: str
    status: str
    content_hash: str
    uri: str
    source: str | None
    filename: str | None
    mime: str | None


def get_tables(metadata) -> tuple[Table, Table]:
    """Return lightweight Table objects for inbox_items and event_outbox.

    Assumes tables exist in the target database.
    """
    inbox_items = Table(
        "inbox_items",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("status", String, nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("uri", Text, nullable=False),
        Column("source", String(64)),
        Column("filename", Text),
        Column("mime", String(128)),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
        Column(
            "updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
        ),
        extend_existing=True,
    )

    event_outbox = Table(
        "event_outbox",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("event_type", String, nullable=False),
        Column("schema_version", String(16), nullable=False),
        Column("idempotency_key", String(128)),
        Column("trace_id", String(64)),
        Column("payload_json", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
        extend_existing=True,
    )

    return inbox_items, event_outbox


def insert_inbox_item(engine: Engine, inbox_items: Table, item: InboxItem) -> InboxItem:
    """Insert a new inbox item with status 'received'; then update to 'validated'.

    Raises IntegrityError on content-hash duplicates (UNIQUE (tenant_id, content_hash)).
    Returns the final persisted item (status validated).
    """
    with engine.begin() as conn:
        # Insert received
        conn.execute(
            insert(inbox_items).values(
                id=item.id,
                tenant_id=item.tenant_id,
                status="received",
                content_hash=item.content_hash,
                uri=item.uri,
                source=item.source,
                filename=item.filename,
                mime=item.mime,
            )
        )
        # Update to validated
        conn.execute(
            update(inbox_items).where(inbox_items.c.id == item.id).values(status="validated")
        )

    # Return the item marked validated
    return InboxItem(
        id=item.id,
        tenant_id=item.tenant_id,
        status="validated",
        content_hash=item.content_hash,
        uri=item.uri,
        source=item.source,
        filename=item.filename,
        mime=item.mime,
    )


def get_inbox_item_by_hash(
    engine: Engine, inbox_items: Table, tenant_id: str, content_hash: str
) -> InboxItem | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(
                inbox_items.c.id,
                inbox_items.c.tenant_id,
                inbox_items.c.status,
                inbox_items.c.content_hash,
                inbox_items.c.uri,
                inbox_items.c.source,
                inbox_items.c.filename,
                inbox_items.c.mime,
            )
            .where(inbox_items.c.tenant_id == tenant_id)
            .where(inbox_items.c.content_hash == content_hash)
        ).fetchone()
    if not row:
        return None
    return InboxItem(
        id=row.id,
        tenant_id=row.tenant_id,
        status=row.status,
        content_hash=row.content_hash,
        uri=row.uri,
        source=row.source,
        filename=row.filename,
        mime=row.mime,
    )
