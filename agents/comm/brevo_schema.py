"""Pydantic models for Brevo webhook event types."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BrevoEventBase(BaseModel):
    """Base model for Brevo events."""

    event: str = Field(..., description="Event type")
    date: datetime = Field(..., description="Event timestamp")
    message_id: str | None = Field(None, alias="message-id", description="Brevo message ID")
    messageId: str | None = Field(None, description="Alternative message ID field")
    email: str | None = Field(None, description="Recipient email")
    reason: str | None = Field(None, description="Reason for bounce/block/etc.")
    tag: str | None = Field(None, description="Email tag")
    sending_ip: str | None = Field(None, alias="sending-ip", description="Sending IP")
    ts: int | None = Field(None, description="Unix timestamp")


class BrevoDeliveredEvent(BrevoEventBase):
    """Delivered event."""

    event: str = Field(default="delivered", description="Event type")


class BrevoSoftBounceEvent(BrevoEventBase):
    """Soft bounce event."""

    event: str = Field(default="soft_bounce", description="Event type")


class BrevoHardBounceEvent(BrevoEventBase):
    """Hard bounce event."""

    event: str = Field(default="hard_bounce", description="Event type")


class BrevoBlockedEvent(BrevoEventBase):
    """Blocked event."""

    event: str = Field(default="blocked", description="Event type")


class BrevoSpamEvent(BrevoEventBase):
    """Spam event."""

    event: str = Field(default="spam", description="Event type")


class BrevoInvalidEvent(BrevoEventBase):
    """Invalid email event."""

    event: str = Field(default="invalid", description="Event type")


class BrevoOpenedEvent(BrevoEventBase):
    """Email opened event."""

    event: str = Field(default="opened", description="Event type")
    ip: str | None = Field(None, description="IP address")
    user_agent: str | None = Field(None, alias="user-agent", description="User agent")


class BrevoClickEvent(BrevoEventBase):
    """Link clicked event."""

    event: str = Field(default="click", description="Event type")
    link: str | None = Field(None, description="Clicked link")
    ip: str | None = Field(None, description="IP address")
    user_agent: str | None = Field(None, alias="user-agent", description="User agent")


class BrevoWebhookPayload(BaseModel):
    """Raw Brevo webhook payload."""

    event: str = Field(..., description="Event type")
    date: datetime = Field(..., description="Event timestamp")
    message_id: str | None = Field(None, alias="message-id")
    messageId: str | None = Field(None)
    email: str | None = Field(None)
    reason: str | None = Field(None)
    tag: str | None = Field(None)
    sending_ip: str | None = Field(None, alias="sending-ip")
    ts: int | None = Field(None)
    ip: str | None = Field(None)
    link: str | None = Field(None)
    user_agent: str | None = Field(None, alias="user-agent")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")

    class Config:
        """Pydantic config."""

        populate_by_name = True


def parse_brevo_event(payload: dict[str, Any]) -> BrevoEventBase:
    """Parse Brevo webhook payload into typed event.

    Args:
        payload: Raw webhook payload

    Returns:
        Typed Brevo event model
    """
    event_type = payload.get("event", "").lower()

    if event_type == "delivered":
        return BrevoDeliveredEvent(**payload)
    elif event_type == "soft_bounce":
        return BrevoSoftBounceEvent(**payload)
    elif event_type == "hard_bounce":
        return BrevoHardBounceEvent(**payload)
    elif event_type == "blocked":
        return BrevoBlockedEvent(**payload)
    elif event_type == "spam":
        return BrevoSpamEvent(**payload)
    elif event_type == "invalid":
        return BrevoInvalidEvent(**payload)
    elif event_type == "opened":
        return BrevoOpenedEvent(**payload)
    elif event_type == "click":
        return BrevoClickEvent(**payload)
    else:
        # Fallback to base model
        return BrevoWebhookPayload(**payload)

