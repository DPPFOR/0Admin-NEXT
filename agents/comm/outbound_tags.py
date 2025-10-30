"""Helper for deterministic outbound message tagging."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

# DNS namespace UUID for deterministic UUID5 generation
DNS_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_message_id(tenant_id: str, invoice_no: str | None = None, ts: datetime | None = None) -> str:
    """Generate deterministic message ID using UUID5.

    Args:
        tenant_id: Tenant UUID
        invoice_no: Invoice number (optional)
        ts: Timestamp (optional, defaults to now)

    Returns:
        Deterministic message ID (UUID string)
    """
    if ts is None:
        ts = datetime.now(UTC)

    # Format timestamp as ISO string
    ts_iso = ts.isoformat()

    # Build input string
    parts = [tenant_id]
    if invoice_no:
        parts.append(invoice_no)
    parts.append(ts_iso)

    input_str = "|".join(parts)

    # Generate UUID5
    message_uuid = uuid5(DNS_NAMESPACE, input_str)

    return str(message_uuid)


def extract_tenant_from_message_id(message_id: str) -> str | None:
    """Extract tenant ID from deterministic message ID (if possible).

    Note: This is not cryptographically secure, but can help with debugging.

    Args:
        message_id: Message ID UUID

    Returns:
        Tenant ID if extractable, None otherwise
    """
    # This is a placeholder - UUID5 is one-way, so we can't reverse it
    # In practice, we'd store the mapping or use message headers
    return None

