"""Business policies for dunning stage determination.

Implements deterministic, functional policies for determining
dunning stages and channels based on invoice data.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from .config import DunningConfig
from .dto import DunningChannel, DunningStage


@dataclass
class OverdueInvoice:
    """Represents an overdue invoice for policy evaluation."""

    invoice_id: str
    tenant_id: str
    invoice_number: str
    due_date: datetime
    amount_cents: int
    customer_email: str | None = None
    customer_name: str | None = None
    created_at: datetime | None = None
    last_dunning_date: datetime | None = None
    dunning_stage: int | None = None

    @property
    def amount_decimal(self) -> Decimal:
        """Get amount as Decimal for calculations."""
        return Decimal(self.amount_cents) / 100

    @property
    def days_overdue(self) -> int:
        """Calculate days overdue from due date."""
        now = datetime.now(UTC)
        return (now - self.due_date).days


class DunningPolicies:
    """Business policies for dunning decisions.

    All methods are pure functions for deterministic behavior.
    """

    def __init__(self, config: DunningConfig):
        """Initialize with configuration.

        Args:
            config: Dunning configuration
        """
        self.config = config

    def determine_dunning_stage(
        self, invoice: OverdueInvoice, now: datetime | None = None
    ) -> DunningStage:
        """Determine dunning stage for overdue invoice.

        Args:
            invoice: Overdue invoice data
            now: Current timestamp (for testing)

        Returns:
            Dunning stage (1, 2, or 3)
        """
        if now is None:
            now = datetime.now(UTC)

        # Calculate days overdue
        days_overdue = (now - invoice.due_date).days

        # Apply grace period
        effective_days = days_overdue - self.config.grace_days

        if effective_days < 0:
            return DunningStage.NONE

        # Determine stage based on thresholds
        if effective_days >= self.config.stage_3_threshold:
            return DunningStage.STAGE_3
        elif effective_days >= self.config.stage_2_threshold:
            return DunningStage.STAGE_2
        elif effective_days >= self.config.stage_1_threshold:
            return DunningStage.STAGE_1
        else:
            return DunningStage.NONE

    def determine_dunning_channel(
        self, invoice: OverdueInvoice, stage: DunningStage
    ) -> DunningChannel:
        """Determine communication channel for dunning notice.

        Args:
            invoice: Overdue invoice data
            stage: Determined dunning stage

        Returns:
            Communication channel
        """
        # Stage 1: Email only
        if stage == DunningStage.STAGE_1:
            return DunningChannel.EMAIL

        # Stage 2: Email + SMS (if available)
        elif stage == DunningStage.STAGE_2:
            if invoice.customer_email:
                return DunningChannel.EMAIL
            else:
                return DunningChannel.LETTER

        # Stage 3: Letter (formal legal notice)
        elif stage == DunningStage.STAGE_3:
            return DunningChannel.LETTER

        # Default fallback
        return DunningChannel.EMAIL

    def should_issue_dunning(
        self, invoice: OverdueInvoice, now: datetime | None = None
    ) -> tuple[bool, str | None]:
        """Check if dunning should be issued for invoice.

        Args:
            invoice: Overdue invoice data
            now: Current timestamp (for testing)

        Returns:
            Tuple of (should_issue, error_message)
        """
        if now is None:
            now = datetime.now(UTC)

        # Check minimum amount
        if invoice.amount_cents < self.config.min_amount_cents:
            min_amount_euro = self.config.min_amount_cents / 100
            return (
                False,
                f"Rechnungsbetrag {invoice.amount_decimal:.2f} EUR unter Mindestbetrag {min_amount_euro:.2f} EUR",
            )

        # Check stop list
        if self.config.is_stop_listed(invoice.invoice_number):
            return False, f"Rechnung {invoice.invoice_number} steht auf der Sperrliste"

        # Check if already at maximum stage
        if invoice.dunning_stage and invoice.dunning_stage >= 3:
            return False, f"Rechnung {invoice.invoice_number} bereits in höchster Mahnstufe (3)"

        # Check grace period
        days_overdue = (now - invoice.due_date).days
        if days_overdue < self.config.grace_days:
            return (
                False,
                f"Rechnung {invoice.invoice_number} noch in Schonfrist ({self.config.grace_days} Tage)",
            )

        # Check if dunning was issued recently (prevent spam)
        if invoice.last_dunning_date:
            days_since_last = (now - invoice.last_dunning_date).days
            if days_since_last < 1:  # Minimum 1 day between dunning notices
                return (
                    False,
                    f"Letzte Mahnung für {invoice.invoice_number} zu recent (vor {days_since_last} Tagen)",
                )

        return True, None

    def calculate_dunning_fee(self, invoice: OverdueInvoice, stage: DunningStage) -> int:
        """Calculate dunning fee in cents.

        Args:
            invoice: Overdue invoice data
            stage: Dunning stage

        Returns:
            Dunning fee in cents
        """
        # Base fee per stage
        base_fees = {
            DunningStage.STAGE_1: 250,  # 2.50 EUR
            DunningStage.STAGE_2: 500,  # 5.00 EUR
            DunningStage.STAGE_3: 1000,  # 10.00 EUR
        }

        return base_fees.get(stage, 0)

    def get_escalation_delay_days(
        self, current_stage: DunningStage, next_stage: DunningStage
    ) -> int:
        """Get days to wait before escalating to next stage.

        Args:
            current_stage: Current dunning stage
            next_stage: Next dunning stage

        Returns:
            Days to wait before escalation
        """
        if current_stage == DunningStage.STAGE_1 and next_stage == DunningStage.STAGE_2:
            return self.config.stage_2_threshold - self.config.stage_1_threshold
        elif current_stage == DunningStage.STAGE_2 and next_stage == DunningStage.STAGE_3:
            return self.config.stage_3_threshold - self.config.stage_2_threshold
        else:
            return 0

    def filter_overdue_invoices(
        self, invoices: list[OverdueInvoice], now: datetime | None = None
    ) -> list[OverdueInvoice]:
        """Filter invoices that should receive dunning.

        Args:
            invoices: List of overdue invoices
            now: Current timestamp (for testing)

        Returns:
            Filtered list of invoices eligible for dunning
        """
        if now is None:
            now = datetime.now(UTC)

        eligible = []

        for invoice in invoices:
            should_issue, error_msg = self.should_issue_dunning(invoice, now)
            if should_issue:
                stage = self.determine_dunning_stage(invoice, now)
                if stage != DunningStage.NONE:
                    eligible.append(invoice)

        return eligible

    def group_by_stage(
        self, invoices: list[OverdueInvoice], now: datetime | None = None
    ) -> dict[DunningStage, list[OverdueInvoice]]:
        """Group invoices by dunning stage.

        Args:
            invoices: List of overdue invoices
            now: Current timestamp (for testing)

        Returns:
            Dictionary mapping stages to invoice lists
        """
        if now is None:
            now = datetime.now(UTC)

        groups = {
            DunningStage.STAGE_1: [],
            DunningStage.STAGE_2: [],
            DunningStage.STAGE_3: [],
        }

        for invoice in invoices:
            should_issue, error_msg = self.should_issue_dunning(invoice, now)
            if should_issue:
                stage = self.determine_dunning_stage(invoice, now)
                if stage in groups:
                    groups[stage].append(invoice)

        return groups
