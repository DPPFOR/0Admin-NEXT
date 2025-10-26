"""Data Transfer Objects for Mahnwesen agent.

Provides type-safe data structures for dunning processes
with validation and serialization support.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
import json


class DunningStage(Enum):
    """Dunning stage enumeration."""
    NONE = 0
    STAGE_1 = 1
    STAGE_2 = 2
    STAGE_3 = 3


class DunningChannel(Enum):
    """Communication channel enumeration."""
    EMAIL = "email"
    LETTER = "letter"
    SMS = "sms"


@dataclass
class OverdueInvoice:
    """Represents an overdue invoice for dunning processing."""
    
    invoice_id: str
    tenant_id: str
    invoice_number: str
    due_date: datetime
    amount_cents: int
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    created_at: Optional[datetime] = None
    last_dunning_date: Optional[datetime] = None
    dunning_stage: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def amount_decimal(self) -> Decimal:
        """Get amount as Decimal for calculations."""
        return Decimal(self.amount_cents) / 100
    
    @property
    def days_overdue(self) -> int:
        """Calculate days overdue from due date."""
        now = datetime.now(timezone.utc)
        return (now - self.due_date).days
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "invoice_id": self.invoice_id,
            "tenant_id": self.tenant_id,
            "invoice_number": self.invoice_number,
            "due_date": self.due_date.isoformat(),
            "amount_cents": self.amount_cents,
            "customer_email": self.customer_email,
            "customer_name": self.customer_name,
            "customer_address": self.customer_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_dunning_date": self.last_dunning_date.isoformat() if self.last_dunning_date else None,
            "dunning_stage": self.dunning_stage,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OverdueInvoice":
        """Create from dictionary."""
        return cls(
            invoice_id=data["invoice_id"],
            tenant_id=data["tenant_id"],
            invoice_number=data["invoice_number"],
            due_date=datetime.fromisoformat(data["due_date"].replace('Z', '+00:00')),
            amount_cents=data["amount_cents"],
            customer_email=data.get("customer_email"),
            customer_name=data.get("customer_name"),
            customer_address=data.get("customer_address"),
            created_at=datetime.fromisoformat(data["created_at"].replace('Z', '+00:00')) if data.get("created_at") else None,
            last_dunning_date=datetime.fromisoformat(data["last_dunning_date"].replace('Z', '+00:00')) if data.get("last_dunning_date") else None,
            dunning_stage=data.get("dunning_stage"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DunningNotice:
    """Represents a dunning notice to be sent."""
    
    notice_id: str = field(default_factory=lambda: str(uuid4()))
    tenant_id: str = ""
    invoice_id: str = ""
    stage: DunningStage = DunningStage.STAGE_1
    channel: DunningChannel = DunningChannel.EMAIL
    subject: str = ""
    content: str = ""
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_address: Optional[str] = None
    due_date: Optional[datetime] = None
    amount_cents: int = 0
    dunning_fee_cents: int = 0
    total_amount_cents: int = 0
    customer_name: Optional[str] = None
    invoice_number: Optional[str] = None
    notice_ref: Optional[str] = None  # For backward compatibility with tests
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    template_version: str = "v1"
    locale: str = "de-DE"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def amount_decimal(self) -> Decimal:
        """Get original amount as Decimal."""
        return Decimal(self.amount_cents) / 100
    
    @property
    def dunning_fee_decimal(self) -> Decimal:
        """Get dunning fee as Decimal."""
        return Decimal(self.dunning_fee_cents) / 100
    
    @property
    def total_amount_decimal(self) -> Decimal:
        """Get total amount as Decimal."""
        return Decimal(self.total_amount_cents) / 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "notice_id": self.notice_id,
            "tenant_id": self.tenant_id,
            "invoice_id": self.invoice_id,
            "stage": self.stage.value,
            "channel": self.channel.value,
            "subject": self.subject,
            "content": self.content,
            "recipient_email": self.recipient_email,
            "recipient_name": self.recipient_name,
            "recipient_address": self.recipient_address,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "amount_cents": self.amount_cents,
            "dunning_fee_cents": self.dunning_fee_cents,
            "total_amount_cents": self.total_amount_cents,
            "customer_name": self.customer_name,
            "invoice_number": self.invoice_number,
            "notice_ref": self.notice_ref,
            "created_at": self.created_at.isoformat(),
            "template_version": self.template_version,
            "locale": self.locale,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DunningNotice":
        """Create from dictionary."""
        return cls(
            notice_id=data["notice_id"],
            tenant_id=data["tenant_id"],
            invoice_id=data["invoice_id"],
            stage=DunningStage(data["stage"]),
            channel=DunningChannel(data["channel"]),
            subject=data["subject"],
            content=data["content"],
            recipient_email=data.get("recipient_email"),
            recipient_name=data.get("recipient_name"),
            recipient_address=data.get("recipient_address"),
            due_date=datetime.fromisoformat(data["due_date"].replace('Z', '+00:00')) if data.get("due_date") else None,
            amount_cents=data["amount_cents"],
            dunning_fee_cents=data["dunning_fee_cents"],
            total_amount_cents=data["total_amount_cents"],
            customer_name=data.get("customer_name"),
            invoice_number=data.get("invoice_number"),
            notice_ref=data.get("notice_ref"),
            created_at=datetime.fromisoformat(data["created_at"].replace('Z', '+00:00')),
            template_version=data.get("template_version", "v1"),
            locale=data.get("locale", "de-DE"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DunningEvent:
    """Represents a dunning event for outbox processing."""
    
    event_id: str = field(default_factory=lambda: str(uuid4()))
    tenant_id: str = ""
    event_type: str = ""
    invoice_id: str = ""
    stage: DunningStage = DunningStage.STAGE_1
    channel: DunningChannel = DunningChannel.EMAIL
    notice_ref: str = ""
    due_date: Optional[datetime] = None
    amount_cents: int = 0
    correlation_id: Optional[str] = None
    schema_version: str = "v1"
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for outbox serialization."""
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "invoice_id": self.invoice_id,
            "stage": self.stage.value,
            "channel": self.channel.value,
            "notice_ref": self.notice_ref,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "amount_cents": self.amount_cents,
            "correlation_id": self.correlation_id,
            "schema_version": self.schema_version,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DunningEvent":
        """Create from dictionary."""
        return cls(
            event_id=data["event_id"],
            tenant_id=data["tenant_id"],
            event_type=data["event_type"],
            invoice_id=data["invoice_id"],
            stage=DunningStage(data["stage"]),
            channel=DunningChannel(data["channel"]),
            notice_ref=data["notice_ref"],
            due_date=datetime.fromisoformat(data["due_date"].replace('Z', '+00:00')) if data.get("due_date") else None,
            amount_cents=data["amount_cents"],
            correlation_id=data.get("correlation_id"),
            schema_version=data.get("schema_version", "v1"),
            payload=data.get("payload", {}),
            created_at=datetime.fromisoformat(data["created_at"].replace('Z', '+00:00')),
        )
    
    def to_outbox_payload(self) -> Dict[str, Any]:
        """Convert to outbox payload format."""
        payload = {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "invoice_id": self.invoice_id,
            "stage": self.stage.value,
            "channel": self.channel.value,
            "notice_ref": self.notice_ref,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "amount": f"{self.amount_cents / 100:.2f}",  # Convert to string with 2 decimal places
            "correlation_id": self.correlation_id,
        }
        
        # Add custom payload data if present
        if hasattr(self, 'payload') and self.payload:
            payload.update(self.payload)
            
        return payload


@dataclass
class DunningResult:
    """Result of dunning processing operation."""
    
    success: bool
    notices_created: int = 0
    events_dispatched: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processing_time_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(self, error: str) -> None:
        """Add error message."""
        self.errors.append(error)
        self.success = False
    
    def add_warning(self, warning: str) -> None:
        """Add warning message."""
        self.warnings.append(warning)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "notices_created": self.notices_created,
            "events_dispatched": self.events_dispatched,
            "errors": self.errors,
            "warnings": self.warnings,
            "processing_time_seconds": self.processing_time_seconds,
            "metadata": self.metadata,
        }
