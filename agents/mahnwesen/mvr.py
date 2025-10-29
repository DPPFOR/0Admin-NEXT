"""MVR (Mahnwesen) Core - Rule engine for dunning stages and limits.

This module implements the core MVR logic for determining dunning stages,
applying limits, and ensuring idempotency in the dunning process.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from .config import DunningConfig


class DunningStage(Enum):
    """Dunning stage enumeration."""

    STAGE_1 = 1
    STAGE_2 = 2
    STAGE_3 = 3


@dataclass
class OverdueInvoice:
    """Overdue invoice data structure."""

    invoice_id: str
    tenant_id: str
    customer_id: str
    customer_name: str
    customer_email: str
    amount_cents: int
    due_date: datetime
    invoice_number: str
    created_at: datetime
    dunning_stage: int | None = None
    last_dunning_sent: datetime | None = None


@dataclass
class DunningDecision:
    """Decision result for dunning processing."""

    should_send: bool
    stage: DunningStage
    reason: str
    idempotency_key: str
    rate_limit_ok: bool


class MVREngine:
    """MVR Core engine for dunning decisions."""

    def __init__(self, config: DunningConfig):
        """Initialize MVR engine with configuration.

        Args:
            config: Dunning configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Rate limiting state (in production, this would be in Redis/DB)
        self._rate_limit_windows: dict[str, list[datetime]] = {}

    def determine_dunning_stage(self, invoice: OverdueInvoice) -> DunningStage:
        """Determine the appropriate dunning stage for an invoice.

        Args:
            invoice: Overdue invoice to evaluate

        Returns:
            Appropriate dunning stage
        """
        if getattr(invoice, "dunning_stage", None) is not None:
            try:
                return DunningStage(invoice.dunning_stage)
            except ValueError:
                pass

        now = datetime.now(UTC)
        days_overdue = (now - invoice.due_date).days

        # Apply grace period
        if days_overdue <= self.config.grace_days:
            return DunningStage.STAGE_1

        # Determine stage based on overdue days
        if days_overdue <= self.config.stage_1_threshold:
            return DunningStage.STAGE_1
        elif days_overdue <= self.config.stage_2_threshold:
            return DunningStage.STAGE_2
        else:
            return DunningStage.STAGE_3

    def should_send_dunning(
        self, invoice: OverdueInvoice, stage: DunningStage, dry_run: bool = False
    ) -> DunningDecision:
        """Determine if dunning should be sent for an invoice.

        Args:
            invoice: Overdue invoice to evaluate
            stage: Dunning stage to send
            dry_run: If True, skip rate limiting checks

        Returns:
            Decision with reasoning and idempotency key
        """
        # Generate deterministic idempotency key
        idempotency_key = self._generate_idempotency_key(
            invoice.tenant_id, invoice.invoice_id, stage
        )

        # Check minimum amount threshold
        if invoice.amount_cents < self.config.min_amount_cents:
            return DunningDecision(
                should_send=False,
                stage=stage,
                reason=f"Amount {invoice.amount_cents} below minimum {self.config.min_amount_cents}",
                idempotency_key=idempotency_key,
                rate_limit_ok=True,
            )

        # Check stop list patterns
        if self.config.is_stop_listed(invoice.invoice_number):
            return DunningDecision(
                should_send=False,
                stage=stage,
                reason=f"Invoice {invoice.invoice_number} is stop-listed",
                idempotency_key=idempotency_key,
                rate_limit_ok=True,
            )

        # Check rate limiting (skip in dry-run)
        if not dry_run:
            rate_limit_ok = self._check_rate_limit(invoice.tenant_id)
            if not rate_limit_ok:
                return DunningDecision(
                    should_send=False,
                    stage=stage,
                    reason="Rate limit exceeded",
                    idempotency_key=idempotency_key,
                    rate_limit_ok=False,
                )
        else:
            rate_limit_ok = True

        # Check if already sent recently (idempotency)
        last_dunning_date = getattr(invoice, "last_dunning_sent", None) or getattr(
            invoice, "last_dunning_date", None
        )
        if last_dunning_date:
            time_since_last = datetime.now(UTC) - last_dunning_date
            if time_since_last < timedelta(hours=24):
                return DunningDecision(
                    should_send=False,
                    stage=stage,
                    reason="Dunning already sent within 24 hours",
                    idempotency_key=idempotency_key,
                    rate_limit_ok=rate_limit_ok,
                )

        return DunningDecision(
            should_send=True,
            stage=stage,
            reason="All checks passed",
            idempotency_key=idempotency_key,
            rate_limit_ok=rate_limit_ok,
        )

    def _generate_idempotency_key(
        self, tenant_id: str, invoice_id: str, stage: DunningStage
    ) -> str:
        """Generate deterministic idempotency key.

        Args:
            tenant_id: Tenant identifier
            invoice_id: Invoice identifier
            stage: Dunning stage

        Returns:
            Deterministic idempotency key
        """
        key_data = f"{tenant_id}|{invoice_id}|{stage.value}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _check_rate_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within rate limits.

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if within rate limits, False otherwise
        """
        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)

        # Get current window for tenant
        if tenant_id not in self._rate_limit_windows:
            self._rate_limit_windows[tenant_id] = []

        window = self._rate_limit_windows[tenant_id]

        # Remove old entries
        window[:] = [ts for ts in window if ts > hour_ago]

        # Check if within limit
        if len(window) >= self.config.max_notices_per_hour:
            return False

        # Add current request
        window.append(now)
        return True

    def process_invoices(
        self, invoices: list[OverdueInvoice], dry_run: bool = False
    ) -> dict[DunningStage, list[tuple[OverdueInvoice, DunningDecision]]]:
        """Process a list of invoices and determine dunning decisions.

        Args:
            invoices: List of overdue invoices
            dry_run: If True, skip rate limiting checks

        Returns:
            Dictionary mapping stages to lists of (invoice, decision) tuples
        """
        results = {DunningStage.STAGE_1: [], DunningStage.STAGE_2: [], DunningStage.STAGE_3: []}

        for invoice in invoices:
            # Determine stage
            stage = self.determine_dunning_stage(invoice)

            # Make decision
            decision = self.should_send_dunning(invoice, stage, dry_run)

            # Group by stage
            results[stage].append((invoice, decision))

            self.logger.debug(
                f"Processed invoice {invoice.invoice_id}",
                extra={
                    "tenant_id": invoice.tenant_id,
                    "stage": stage.name,
                    "should_send": decision.should_send,
                    "reason": decision.reason,
                    "idempotency_key": decision.idempotency_key,
                },
            )

        return results

    def get_rate_limit_status(self, tenant_id: str) -> dict[str, int]:
        """Get current rate limit status for tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary with rate limit status
        """
        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)

        if tenant_id not in self._rate_limit_windows:
            return {
                "current_count": 0,
                "max_per_hour": self.config.max_notices_per_hour,
                "remaining": self.config.max_notices_per_hour,
            }

        window = self._rate_limit_windows[tenant_id]
        current_count = len([ts for ts in window if ts > hour_ago])

        return {
            "current_count": current_count,
            "max_per_hour": self.config.max_notices_per_hour,
            "remaining": max(0, self.config.max_notices_per_hour - current_count),
        }

    def reset_rate_limits(self, tenant_id: str | None = None):
        """Reset rate limits for tenant or all tenants.

        Args:
            tenant_id: Specific tenant to reset, or None for all
        """
        if tenant_id:
            if tenant_id in self._rate_limit_windows:
                del self._rate_limit_windows[tenant_id]
        else:
            self._rate_limit_windows.clear()

        self.logger.info(f"Rate limits reset for {'all tenants' if not tenant_id else tenant_id}")
