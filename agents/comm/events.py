"""Normalized communication events and Brevo mapper."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from agents.comm.brevo_schema import BrevoEventBase, parse_brevo_event


class CommEvent(BaseModel):
    """Normalized communication event."""

    event_type: str = Field(..., description="Normalized event type")
    tenant_id: str = Field(..., description="Tenant UUID")
    message_id: str | None = Field(None, description="Provider message ID")
    recipient: str | None = Field(None, description="Recipient email (PII)")
    reason: str | None = Field(None, description="Reason for bounce/block/etc.")
    ts: datetime = Field(..., description="Event timestamp (UTC)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    provider: str = Field(default="brevo", description="Provider name")
    provider_event_id: str | None = Field(None, description="Provider-specific event ID")


class BrevoEventMapper:
    """Maps Brevo events to normalized CommEvent."""

    @staticmethod
    def map_to_comm_event(
        brevo_event: BrevoEventBase | dict[str, Any],
        tenant_id: str,
        provider_event_id: str | None = None,
    ) -> CommEvent:
        """Map Brevo event to normalized CommEvent.

        Args:
            brevo_event: Brevo event (parsed or raw dict)
            tenant_id: Tenant UUID
            provider_event_id: Optional provider-specific event ID

        Returns:
            Normalized CommEvent
        """
        if isinstance(brevo_event, dict):
            brevo_event = parse_brevo_event(brevo_event)

        # Extract message ID
        message_id = brevo_event.message_id or brevo_event.messageId

        # Extract recipient
        recipient = brevo_event.email

        # Extract timestamp
        ts = brevo_event.date
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        else:
            ts = datetime.now(UTC)

        # Normalize event type
        event_type = brevo_event.event.lower()

        # Extract reason
        reason = brevo_event.reason

        # Build metadata
        metadata: dict[str, Any] = {}
        if brevo_event.tag:
            metadata["tag"] = brevo_event.tag
        if brevo_event.sending_ip:
            metadata["sending_ip"] = brevo_event.sending_ip
        if hasattr(brevo_event, "ip") and brevo_event.ip:
            metadata["ip"] = brevo_event.ip
        if hasattr(brevo_event, "link") and brevo_event.link:
            metadata["link"] = brevo_event.link
        if hasattr(brevo_event, "user_agent") and brevo_event.user_agent:
            metadata["user_agent"] = brevo_event.user_agent

        return CommEvent(
            event_type=event_type,
            tenant_id=tenant_id,
            message_id=message_id,
            recipient=recipient,
            reason=reason,
            ts=ts,
            metadata=metadata,
            provider="brevo",
            provider_event_id=provider_event_id,
        )

    @staticmethod
    def extract_tenant_id(
        payload: dict[str, Any], tenant_header: str | None = None
    ) -> str | None:
        """Extract tenant ID from payload or header.

        Args:
            payload: Raw webhook payload
            tenant_header: X-Tenant-ID header value

        Returns:
            Tenant ID or None
        """
        if tenant_header:
            try:
                # Validate UUID format
                UUID(tenant_header)
                return tenant_header
            except ValueError:
                pass

        # Check payload metadata
        if metadata := payload.get("metadata"):
            if isinstance(metadata, dict):
                tenant_id = metadata.get("tenant_id") or metadata.get("tenantId")
                if tenant_id:
                    try:
                        UUID(str(tenant_id))
                        return str(tenant_id)
                    except ValueError:
                        pass

        return None

