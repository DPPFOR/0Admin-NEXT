"""Client implementations for Mahnwesen agent.

Provides Read-API and Outbox clients with proper error handling,
rate limiting, and multi-tenant support.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..shared.flock_client import FlockClient
from .config import DunningConfig
from .dto import DunningEvent, DunningStage, OverdueInvoice


@dataclass
class CursorPagination:
    """Cursor-based pagination parameters."""

    cursor: str | None = None
    limit: int = 100
    direction: str = "desc"  # desc or asc

    def to_dict(self) -> dict[str, Any]:
        """Convert to query parameters."""
        params = {"limit": self.limit, "direction": self.direction}
        if self.cursor:
            params["cursor"] = self.cursor
        return params


@dataclass
class OverdueInvoicesResponse:
    """Response from overdue invoices query."""

    invoices: list[OverdueInvoice]
    next_cursor: str | None = None
    total_count: int | None = None
    has_more: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OverdueInvoicesResponse":
        """Create from API response."""
        invoices = [OverdueInvoice.from_dict(inv) for inv in data.get("invoices", [])]
        return cls(
            invoices=invoices,
            next_cursor=data.get("next_cursor"),
            total_count=data.get("total_count"),
            has_more=data.get("has_more", False),
        )


class ReadApiClient:
    """Client for reading overdue invoices from the API.

    Provides multi-tenant support with proper header handling
    and cursor-based pagination.
    """

    def __init__(self, config: DunningConfig):
        """Initialize Read-API client.

        Args:
            config: Dunning configuration
        """
        self.config = config
        self.client = FlockClient(
            base_url=config.read_api_base_url, timeout=config.read_api_timeout
        )
        self.logger = logging.getLogger(__name__)

    def _get_headers(self, correlation_id: str | None = None) -> dict[str, str]:
        """Get request headers with tenant ID.

        Args:
            correlation_id: Optional correlation ID

        Returns:
            Headers dictionary
        """
        headers = {
            "X-Tenant-Id": self.config.tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        return headers

    def get_overdue_invoices(
        self, pagination: CursorPagination | None = None, correlation_id: str | None = None
    ) -> OverdueInvoicesResponse:
        """Get overdue invoices for the tenant.

        Args:
            pagination: Pagination parameters
            correlation_id: Optional correlation ID

        Returns:
            Response with overdue invoices

        Raises:
            Exception: On API error
        """
        if pagination is None:
            pagination = CursorPagination()

        try:
            response = self.client.get(
                endpoint="/api/v1/invoices/overdue",
                headers=self._get_headers(correlation_id),
                timeout=self.config.read_api_timeout,
                correlation_id=correlation_id,
            )

            if not response.is_success:
                error_msg = f"API error {response.status_code}: {response.data}"
                self.logger.error(
                    "Failed to get overdue invoices",
                    extra={
                        "status_code": response.status_code,
                        "error": response.data,
                        "correlation_id": correlation_id,
                    },
                )
                raise Exception(error_msg)

            return OverdueInvoicesResponse.from_dict(response.data)

        except Exception as e:
            self.logger.error(
                "Read-API request failed", extra={"error": str(e), "correlation_id": correlation_id}
            )
            raise

    def get_invoice_details(
        self, invoice_id: str, correlation_id: str | None = None
    ) -> OverdueInvoice | None:
        """Get detailed invoice information.

        Args:
            invoice_id: Invoice ID
            correlation_id: Optional correlation ID

        Returns:
            Invoice details or None if not found
        """
        try:
            response = self.client.get(
                endpoint=f"/api/v1/invoices/{invoice_id}",
                headers=self._get_headers(correlation_id),
                timeout=self.config.read_api_timeout,
                correlation_id=correlation_id,
            )

            if response.status_code == 404:
                return None

            if not response.is_success:
                error_msg = f"API error {response.status_code}: {response.data}"
                self.logger.error(
                    "Failed to get invoice details",
                    extra={
                        "invoice_id": invoice_id,
                        "status_code": response.status_code,
                        "error": response.data,
                        "correlation_id": correlation_id,
                    },
                )
                raise Exception(error_msg)

            return OverdueInvoice.from_dict(response.data)

        except Exception as e:
            self.logger.error(
                "Failed to get invoice details",
                extra={"invoice_id": invoice_id, "error": str(e), "correlation_id": correlation_id},
            )
            raise

    def health_check(self) -> bool:
        """Check if Read-API is healthy.

        Returns:
            True if API is healthy
        """
        try:
            response = self.client.get(endpoint="/healthz", headers=self._get_headers(), timeout=5)
            return response.is_success
        except Exception:
            return False


class NoOpPublisher:
    """No-operation publisher for dry-run mode.

    Provides the same interface as OutboxClient but performs no actual
    outbox writes. Used in dry-run scenarios to simulate publishing
    without side effects.
    """

    def __init__(self):
        """Initialize NoOp publisher."""
        self.logger = logging.getLogger(__name__)

    def publish_dunning_issued(self, event: DunningEvent) -> bool:
        """Simulate publishing dunning event (no-op).

        Args:
            event: Dunning event

        Returns:
            False by default (no events published)
        """
        self.logger.debug(
            "DRY RUN: Would publish dunning event",
            extra={
                "event_type": event.event_type,
                "tenant_id": event.tenant_id,
                "invoice_id": event.invoice_id,
                "stage": event.stage.value,
            },
        )
        return False


class OutboxClient:
    """Client for publishing dunning events to the outbox.

    Provides idempotency and retry logic for event publishing.
    """

    def __init__(self, config: DunningConfig):
        """Initialize Outbox client.

        Args:
            config: Dunning configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._sent_events: set[str] = set()
        self._sent_events_path = (
            Path("artifacts/reports/mahnwesen") / self.config.tenant_id / "outbox" / "sent.json"
        )
        self._load_sent_events()

    def _generate_idempotency_key(
        self, tenant_id: str, invoice_id: str, stage: DunningStage
    ) -> str:
        """Generate idempotency key for event.

        Args:
            tenant_id: Tenant ID
            invoice_id: Invoice ID
            stage: Dunning stage

        Returns:
            Idempotency key
        """
        # Normalize inputs for deterministic hashing
        normalized_tenant = tenant_id.strip().lower()
        normalized_invoice = invoice_id.strip().lower()
        normalized_stage = str(stage.value).strip()

        # Create canonical key
        canonical_key = f"{normalized_tenant}|{normalized_invoice}|{normalized_stage}"

        # Generate SHA-256 hash
        return hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()

    def _create_outbox_payload(self, event: DunningEvent, idempotency_key: str) -> dict[str, Any]:
        """Create outbox payload for event.

        Args:
            event: Dunning event
            idempotency_key: Idempotency key

        Returns:
            Outbox payload
        """
        return {
            "tenant_id": event.tenant_id,
            "event_type": event.event_type,
            "payload_json": event.to_outbox_payload(),
            "idempotency_key": idempotency_key,
            "schema_version": event.schema_version,
            "status": "pending",
            "retry_count": 0,
            "created_at": event.created_at.isoformat(),
            "updated_at": event.created_at.isoformat(),
        }

    def publish_dunning_issued(
        self, event: DunningEvent, correlation_id: str | None = None, dry_run: bool = False
    ) -> bool:
        """Publish DUNNING_ISSUED event.

        Args:
            event: Dunning event
            correlation_id: Optional correlation ID
            dry_run: If True, simulate without actual outbox write

        Returns:
            True if event was published successfully
        """
        try:
            # Generate idempotency key
            idempotency_key = self._generate_idempotency_key(
                event.tenant_id, event.invoice_id, event.stage
            )

            # Create outbox payload
            payload = self._create_outbox_payload(event, idempotency_key)

            # Log event (without PII)
            self.logger.info(
                "Publishing dunning event",
                extra={
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "invoice_id": event.invoice_id,
                    "stage": event.stage.value,
                    "idempotency_key": idempotency_key[:8] + "...",  # Truncated for security
                    "correlation_id": correlation_id,
                },
            )

            # In dry run mode, don't actually write to outbox
            if not dry_run:
                # In a real implementation, this would write to the outbox table
                # For now, we'll simulate the operation
                self._simulate_outbox_write(payload)
            else:
                # Dry run: just log that we would publish
                self.logger.info(
                    "DRY RUN: Would publish dunning event",
                    extra={
                        "event_type": event.event_type,
                        "tenant_id": event.tenant_id,
                        "invoice_id": event.invoice_id,
                        "stage": event.stage.value,
                    },
                )

            return True

        except Exception as e:
            self.logger.error(
                "Failed to publish dunning event",
                extra={
                    "error": str(e),
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "invoice_id": event.invoice_id,
                    "correlation_id": correlation_id,
                },
            )
            return False

    def publish_dunning_escalated(
        self,
        event: DunningEvent,
        from_stage: DunningStage,
        reason: str,
        correlation_id: str | None = None,
    ) -> bool:
        """Publish DUNNING_ESCALATED event.

        Args:
            event: Dunning event
            from_stage: Previous dunning stage
            reason: Escalation reason
            correlation_id: Optional correlation ID

        Returns:
            True if event was published successfully
        """
        try:
            # Add escalation data to event payload
            if not hasattr(event, "payload"):
                event.payload = {}
            event.payload.update(
                {
                    "from_stage": from_stage.value,
                    "reason": reason,
                    "escalated_at": datetime.now(UTC).isoformat(),
                }
            )

            # Generate idempotency key
            idempotency_key = self._generate_idempotency_key(
                event.tenant_id, event.invoice_id, event.stage
            )

            # Create outbox payload
            payload = self._create_outbox_payload(event, idempotency_key)

            # Log event
            self.logger.info(
                "Publishing dunning escalation event",
                extra={
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "invoice_id": event.invoice_id,
                    "from_stage": from_stage.value,
                    "to_stage": event.stage.value,
                    "reason": reason,
                    "correlation_id": correlation_id,
                },
            )

            # Simulate outbox write
            self._simulate_outbox_write(payload)

            return True

        except Exception as e:
            self.logger.error(
                "Failed to publish escalation event",
                extra={
                    "error": str(e),
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "invoice_id": event.invoice_id,
                    "correlation_id": correlation_id,
                },
            )
            return False

    def publish_dunning_resolved(
        self,
        event: DunningEvent,
        resolution: str,
        resolved_at: datetime,
        correlation_id: str | None = None,
    ) -> bool:
        """Publish DUNNING_RESOLVED event.

        Args:
            event: Dunning event
            resolution: Resolution reason
            resolved_at: Resolution timestamp
            correlation_id: Optional correlation ID

        Returns:
            True if event was published successfully
        """
        try:
            # Add resolution data to event payload
            if not hasattr(event, "payload"):
                event.payload = {}
            event.payload.update({"resolution": resolution, "resolved_at": resolved_at.isoformat()})

            # Generate idempotency key
            idempotency_key = self._generate_idempotency_key(
                event.tenant_id, event.invoice_id, event.stage
            )

            # Create outbox payload
            payload = self._create_outbox_payload(event, idempotency_key)

            # Log event
            self.logger.info(
                "Publishing dunning resolution event",
                extra={
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "invoice_id": event.invoice_id,
                    "resolution": resolution,
                    "resolved_at": resolved_at.isoformat(),
                    "correlation_id": correlation_id,
                },
            )

            # Simulate outbox write
            self._simulate_outbox_write(payload)

            return True

        except Exception as e:
            self.logger.error(
                "Failed to publish resolution event",
                extra={
                    "error": str(e),
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "invoice_id": event.invoice_id,
                    "correlation_id": correlation_id,
                },
            )
            return False

    def _simulate_outbox_write(self, payload: dict[str, Any]) -> None:
        """Simulate outbox write operation.

        In a real implementation, this would write to the database.
        For testing purposes, we'll just log the operation.
        """
        self.logger.debug(
            "Simulated outbox write",
            extra={
                "tenant_id": payload["tenant_id"],
                "event_type": payload["event_type"],
                "idempotency_key": payload["idempotency_key"][:8] + "...",
            },
        )
        self._record_sent_event(payload["idempotency_key"])

    def check_duplicate_event(self, tenant_id: str, invoice_id: str, stage: DunningStage) -> bool:
        """Check if event already exists (idempotency check).

        Args:
            tenant_id: Tenant ID
            invoice_id: Invoice ID
            stage: Dunning stage

        Returns:
            True if event already exists
        """
        idempotency_key = self._generate_idempotency_key(tenant_id, invoice_id, stage)

        # In a real implementation, this would query the outbox table
        # For testing, we'll simulate the check
        self.logger.debug(
            "Checking for duplicate event",
            extra={
                "tenant_id": tenant_id,
                "invoice_id": invoice_id,
                "stage": stage.value,
                "idempotency_key": idempotency_key[:8] + "...",
            },
        )

        return idempotency_key in self._sent_events

    def _record_sent_event(self, idempotency_key: str) -> None:
        self._sent_events.add(idempotency_key)
        self._persist_sent_events()

    def _load_sent_events(self) -> None:
        try:
            if self._sent_events_path.exists():
                with self._sent_events_path.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                self._sent_events = set(data.get("keys", []))
        except Exception as exc:
            self.logger.warning(
                "Failed to load sent events cache", extra={"error": str(exc)}
            )

    def _persist_sent_events(self) -> None:
        try:
            self._sent_events_path.parent.mkdir(parents=True, exist_ok=True)
            with self._sent_events_path.open("w", encoding="utf-8") as fp:
                json.dump({"keys": sorted(self._sent_events)}, fp, indent=2)
        except Exception as exc:
            self.logger.warning(
                "Failed to persist sent events cache", extra={"error": str(exc)}
            )
