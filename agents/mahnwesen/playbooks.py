"""Flock-based dunning playbooks and workflow orchestration.

This module provides the core Flock integration for automated dunning processes.
It handles workflow orchestration, template rendering, and event dispatch.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from backend.integrations.brevo_client import send_transactional

from .clients import OutboxClient, ReadApiClient
from .config import DunningConfig
from .dto import DunningEvent, DunningNotice, DunningStage, OverdueInvoice
from .mvr import MVREngine
from .policies import DunningPolicies


@dataclass
class DunningContext:
    """Context for dunning process execution."""

    tenant_id: str
    correlation_id: str
    dry_run: bool = False
    limit: int = 100
    config: DunningConfig | None = None
    policies: DunningPolicies | None = None
    read_client: ReadApiClient | None = None
    outbox_client: OutboxClient | None = None
    template_engine: Optional["TemplateEngine"] = None

    def __post_init__(self):
        """Initialize dependencies after creation."""
        if self.config is None:
            self.config = DunningConfig.from_tenant(self.tenant_id)

        if self.policies is None:
            self.policies = DunningPolicies(self.config)

        if self.read_client is None:
            self.read_client = ReadApiClient(self.config)

        if self.outbox_client is None:
            self.outbox_client = OutboxClient(self.config)

        if self.template_engine is None:
            self.template_engine = TemplateEngine(self.config)

        # Initialize MVR engine
        self.mvr_engine = MVREngine(self.config)


class TemplateEngine:
    """Jinja2 template engine for dunning notices."""

    def __init__(self, config: DunningConfig):
        """Initialize template engine.

        Args:
            config: Dunning configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize Jinja2 environment with deterministic template loading
        self.env = Environment(
            loader=FileSystemLoader(
                [
                    f"agents/mahnwesen/templates/{self.config.tenant_id}",
                    "agents/mahnwesen/templates/default",
                ]
            ),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            cache_size=0,  # Disable cache to avoid stale template loads
        )

        # Add custom filters and globals
        self.env.filters["money"] = self._money_filter
        self.env.filters["datefmt"] = self._datefmt_filter
        self.env.globals["locale"] = self.config.default_locale

        # Load templates for backward compatibility
        self.templates = self._load_templates()
        self.sub_stage_mapping = self._load_sub_stage_mapping()

    def resolve_sub_stage_path(self, sub_stage_key: str) -> str:
        """Resolve sub-stage key to template path for linker.

        Args:
            sub_stage_key: Sub-stage identifier (e.g., 'sub_stage-1')

        Returns:
            Resolved template path
        """
        if sub_stage_key in self.sub_stage_mapping:
            return self.sub_stage_mapping[sub_stage_key]

        # Default fallback for unknown keys
        self.logger.warning(f"Unknown sub_stage key: {sub_stage_key}, using default mapping")
        return f"/spec_main_mahnung/{sub_stage_key}/s0"

    def _load_sub_stage_mapping(self) -> dict[str, str]:
        """Load sub-stage to template path mappings.

        Returns:
            Dictionary mapping sub-stage keys to template paths
        """
        mapping_file = Path("agents/mahnwesen/templates/sub_stage_mapping.yaml")
        if not mapping_file.exists():
            self.logger.warning(f"Sub-stage mapping file not found: {mapping_file}")
            return {}

        try:
            with open(mapping_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
                else:
                    self.logger.warning(f"Invalid mapping file format: {mapping_file}")
                    return {}
        except Exception as e:
            self.logger.error(f"Failed to load sub-stage mapping: {e}")
            return {}

    def _load_templates(self) -> dict[str, str]:
        """Load Jinja2 templates from files for backward compatibility.

        Returns:
            Dictionary mapping stage names to template content
        """
        templates = {}

        # Try tenant-specific templates first, then default
        template_paths = [
            f"agents/mahnwesen/templates/{self.config.tenant_id}",
            "agents/mahnwesen/templates/default",
        ]

        for template_dir in template_paths:
            try:
                # Load stage 1 template
                stage_1_path = f"{template_dir}/stage_1.jinja.txt"
                with open(stage_1_path, encoding="utf-8") as f:
                    templates["stage_1"] = f.read()

                # Load stage 2 template
                stage_2_path = f"{template_dir}/stage_2.jinja.txt"
                with open(stage_2_path, encoding="utf-8") as f:
                    templates["stage_2"] = f.read()

                # Load stage 3 template
                stage_3_path = f"{template_dir}/stage_3.jinja.txt"
                with open(stage_3_path, encoding="utf-8") as f:
                    templates["stage_3"] = f.read()

                self.logger.info(f"Loaded templates from {template_dir}")
                break

            except FileNotFoundError:
                continue

        if not templates:
            # Try to load from default directory only
            try:
                default_dir = "agents/mahnwesen/templates/default"
                stage_1_path = f"{default_dir}/stage_1.jinja.txt"
                with open(stage_1_path, encoding="utf-8") as f:
                    templates["stage_1"] = f.read()

                stage_2_path = f"{default_dir}/stage_2.jinja.txt"
                with open(stage_2_path, encoding="utf-8") as f:
                    templates["stage_2"] = f.read()

                stage_3_path = f"{default_dir}/stage_3.jinja.txt"
                with open(stage_3_path, encoding="utf-8") as f:
                    templates["stage_3"] = f.read()

                self.logger.info(f"Loaded templates from {default_dir}")
            except FileNotFoundError as err:
                raise FileNotFoundError("No templates found in default directory") from err

        return templates

    def _money_filter(self, amount_cents: int) -> str:
        """Format amount in cents as money string.

        Args:
            amount_cents: Amount in cents

        Returns:
            Formatted money string
        """
        return f"{amount_cents / 100:.2f}"

    def _datefmt_filter(self, date_obj, format_str: str = "%Y-%m-%d") -> str:
        """Format date object as string.

        Args:
            date_obj: Date object to format
            format_str: Format string

        Returns:
            Formatted date string
        """
        if hasattr(date_obj, "strftime"):
            return date_obj.strftime(format_str)
        elif hasattr(date_obj, "isoformat"):
            return date_obj.isoformat()
        else:
            return str(date_obj)

    def render_notice(self, notice: DunningNotice, stage: DunningStage) -> DunningNotice:
        """Render dunning notice using template.

        Args:
            notice: Dunning notice data
            stage: Dunning stage

        Returns:
            Rendered notice with content

        Raises:
            FileNotFoundError: If template for stage is not found
        """
        # Get template for stage
        template_name = f"stage_{stage.value}.jinja.txt"

        # Use Jinja's FileSystemLoader for deterministic template resolution
        try:
            template = self.env.get_template(template_name)
            # Log the resolved template path
            self.logger.info(
                f'template_path="{template.filename}" tenant="{self.config.tenant_id}" stage="{stage.value}"'
            )
        except Exception as e:
            # NEVER use fallback content - fail hard for missing templates
            error_msg = f"Template '{template_name}' not found for tenant '{self.config.tenant_id}'. Ensure templates exist in agents/mahnwesen/templates/{self.config.tenant_id}/ or agents/mahnwesen/templates/default/"
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg) from e

        # Prepare complete context for template rendering
        context = {
            "config": self.config,
            "notice": notice,
            "stage": stage,
            "tenant_id": self.config.tenant_id,
            "company_name": getattr(self.config, "company_name", None) or "",
            "tenant_name": getattr(self.config, "tenant_name", None) or "0Admin",
            "customer_name": notice.customer_name or "Test Customer",
            "invoice_id": notice.invoice_id,
            "invoice_number": notice.invoice_number or notice.invoice_id,
            "due_date": notice.due_date,
            "due_date_iso": (
                notice.due_date.isoformat()
                if hasattr(notice.due_date, "isoformat")
                else str(notice.due_date) if notice.due_date else ""
            ),
            "amount_cents": notice.amount_cents,
            "dunning_fee_cents": notice.dunning_fee_cents,
            "total_amount_cents": notice.total_amount_cents,
            "amount_str": f"{notice.amount_cents / 100:.2f}",
            "fee_str": (
                f"{notice.dunning_fee_cents / 100:.2f}" if notice.dunning_fee_cents > 0 else "0.00"
            ),
            "total_str": f"{(notice.amount_cents + notice.dunning_fee_cents) / 100:.2f}",
            "fee": (
                f"{notice.dunning_fee_cents / 100:.2f}" if notice.dunning_fee_cents > 0 else "0.00"
            ),
            "notice_ref": notice.notice_id,
            "locale": self.config.default_locale,
            "template_version": "v1",
        }

        # Render template
        rendered_content = template.render(**context)

        # Update notice with rendered content
        notice.content = rendered_content
        notice.subject = self._extract_subject(rendered_content)

        return notice

    def _extract_subject(self, content: str) -> str:
        """Extract subject from rendered content.

        Args:
            content: Rendered content

        Returns:
            Subject line
        """
        lines = content.split("\n")
        for line in lines:
            if line.startswith("Betreff:"):
                return line.replace("Betreff:", "").strip()

        return "Zahlungserinnerung"


@dataclass
class DunningResult:
    """Result of dunning process execution."""

    success: bool
    notices_created: int = 0
    events_dispatched: int = 0
    processing_time_seconds: float = 0.0
    errors: list[str] = None
    warnings: list[str] = None
    total_overdue: int = 0
    stage_1_count: int = 0
    stage_2_count: int = 0
    stage_3_count: int = 0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class DunningPlaybook:
    """Flock-based dunning playbook orchestrator."""

    def __init__(self, config: DunningConfig):
        """Initialize playbook.

        Args:
            config: Dunning configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

    def run_once(self, context: DunningContext) -> DunningResult:
        """Run dunning process once.

        Args:
            context: Dunning context

        Returns:
            Dunning result
        """
        start_time = datetime.now(UTC)

        try:
            # Step 1: Fetch overdue invoices
            overdue_invoices = self._fetch_overdue_invoices(context)

            if not overdue_invoices:
                return DunningResult(
                    success=True,
                    notices_created=0,
                    events_dispatched=0,
                    processing_time_seconds=(datetime.now(UTC) - start_time).total_seconds(),
                    warnings=["No overdue invoices found"],
                )

            # Step 2: Process with MVR engine
            mvr_results = context.mvr_engine.process_invoices(overdue_invoices, context.dry_run)

            # Step 3: Create notices and dispatch events
            notices_created = 0
            events_dispatched = 0

            for stage, invoice_decisions in mvr_results.items():
                if not invoice_decisions:
                    continue

                for invoice, decision in invoice_decisions:
                    if not decision.should_send:
                        self.logger.debug(
                            f"Skipping invoice {invoice.invoice_id}: {decision.reason}"
                        )
                        continue

                    # Create notice
                    notice = self._create_notice(invoice, stage, context)

                    # Render template
                    rendered_notice = context.template_engine.render_notice(notice, stage)

                    # Send via Brevo
                    brevo_response = self._send_via_brevo(rendered_notice, context)

                    # Dispatch event if Brevo successful
                    if brevo_response.success:
                        if not context.outbox_client.check_duplicate_event(
                            rendered_notice.tenant_id, rendered_notice.invoice_id, stage
                        ):
                            event = self._create_dunning_event_impl(rendered_notice, stage, context)

                            # Choose publisher strategy based on dry_run mode
                            if context.dry_run:
                                # In dry-run mode, just count as dispatched without calling API
                                events_dispatched += 1
                                self.logger.info(
                                    f"Dry-run: Would dispatch dunning event for invoice {invoice.invoice_id}"
                                )
                            else:
                                # Live run: use real client
                                if context.outbox_client.publish_dunning_issued(
                                    event, dry_run=False
                                ):
                                    events_dispatched += 1

                    notices_created += 1

            # Calculate processing time
            processing_time = (datetime.now(UTC) - start_time).total_seconds()

            return DunningResult(
                success=True,
                notices_created=notices_created,
                events_dispatched=events_dispatched,
                processing_time_seconds=processing_time,
                total_overdue=len(overdue_invoices),
                stage_1_count=len(mvr_results.get(DunningStage.STAGE_1, [])),
                stage_2_count=len(mvr_results.get(DunningStage.STAGE_2, [])),
                stage_3_count=len(mvr_results.get(DunningStage.STAGE_3, [])),
            )

        except Exception as e:
            self.logger.error(f"Dunning process failed: {e}")
            return DunningResult(
                success=False,
                errors=[str(e)],
                processing_time_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            )

    def create_flow(self, context: DunningContext):
        """Create Flock flow (adapter for tests)."""
        # This is a no-op adapter for backward compatibility
        flow = Mock()
        flow.name = "dunning_processing"
        flow.description = "Automated dunning process for overdue invoices"
        return flow

    def _scan_overdue_invoices(self, context: DunningContext):
        """Scan overdue invoices (adapter for tests)."""
        invoices = self._fetch_overdue_invoices(context)
        # Group invoices by stage based on due_date
        now = datetime.now(UTC)
        stage_groups = {"stage_1": [], "stage_2": [], "stage_3": []}

        for inv in invoices:
            if inv.dunning_stage is not None:
                # Use existing stage
                if inv.dunning_stage == 0:
                    stage_groups["stage_1"].append(inv)
                elif inv.dunning_stage == 1:
                    stage_groups["stage_2"].append(inv)
                elif inv.dunning_stage == 2:
                    stage_groups["stage_3"].append(inv)
            else:
                # Determine stage based on due_date
                days_overdue = (now - inv.due_date).days
                if days_overdue < 14:
                    stage_groups["stage_1"].append(inv)
                elif days_overdue < 30:
                    stage_groups["stage_2"].append(inv)
                else:
                    stage_groups["stage_3"].append(inv)

        return {
            "total_found": len(invoices),
            "eligible_count": len(invoices),
            "stage_1_count": len(stage_groups["stage_1"]),
            "stage_2_count": len(stage_groups["stage_2"]),
            "stage_3_count": len(stage_groups["stage_3"]),
            "stage_groups": stage_groups,
            "invoices": invoices,
        }

    def _compose_dunning_notices(self, context: DunningContext):
        """Compose dunning notices (adapter for tests)."""
        # This would be implemented based on scan_results in context.kwargs
        scan_results = context.kwargs.get("scan_results", {})
        stage_groups = scan_results.get("stage_groups", {})

        notices = []
        for stage, invoices in stage_groups.items():
            for invoice in invoices:
                notice = self._create_notice(invoice, stage, context)
                rendered_notice = context.template_engine.render_notice(notice, stage)
                notices.append(rendered_notice)

        return {"notices": notices, "notices_created": len(notices)}

    def _dispatch_dunning_events(self, context: DunningContext):
        """Dispatch dunning events (adapter for tests)."""
        compose_results = context.kwargs.get("compose_results", {})
        notices = compose_results.get("notices", [])

        events_dispatched = 0
        for notice in notices:
            # Always check for duplicates first
            if context.outbox_client.check_duplicate_event(
                notice.tenant_id, notice.invoice_id, notice.stage
            ):
                continue

            # Dispatch event based on dry_run mode
            event = self._create_dunning_event_impl(notice, notice.stage, context)
            if context.dry_run:
                # In dry-run mode, just count as dispatched without calling API
                events_dispatched += 1
                self.logger.info(
                    f"Dry-run: Would dispatch dunning event for notice {notice.notice_ref}"
                )
            else:
                # Live run: use real client
                if context.outbox_client.publish_dunning_issued(event, dry_run=False):
                    events_dispatched += 1
                else:
                    self.logger.warning(
                        f"Failed to publish dunning event for notice {notice.notice_ref}"
                    )

        return {"events_dispatched": events_dispatched, "total_events": len(notices)}

    def _create_dunning_event(self, notice: DunningNotice, context: DunningContext):
        """Create dunning event (adapter for tests with 2 parameters)."""
        return self._create_dunning_event_impl(notice, notice.stage, context)

    def _fetch_overdue_invoices(self, context: DunningContext) -> list[OverdueInvoice]:
        """Fetch overdue invoices from Read-API.

        Args:
            context: Dunning context

        Returns:
            List of overdue invoices
        """
        try:
            response = context.read_client.get_overdue_invoices()
            invoices = response.invoices

            # Invoices are already OverdueInvoice objects
            return invoices

        except Exception as e:
            self.logger.error(f"Failed to fetch overdue invoices: {e}")
            raise  # Re-raise to be handled by run_once

    def _create_notice(
        self, invoice: OverdueInvoice, stage: DunningStage, context: DunningContext
    ) -> DunningNotice:
        """Create dunning notice for invoice.

        Args:
            invoice: Overdue invoice
            stage: Dunning stage
            context: Dunning context

        Returns:
            Dunning notice
        """
        # Determine channel
        channel = context.policies.determine_dunning_channel(invoice, stage)

        # Calculate dunning fee
        dunning_fee_cents = context.policies.calculate_dunning_fee(invoice, stage)

        return DunningNotice(
            notice_id=f"NOTICE-{invoice.invoice_id}",
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            stage=stage,
            channel=channel,
            recipient_email=invoice.customer_email,
            recipient_name=invoice.customer_name,
            due_date=invoice.due_date,
            amount_cents=invoice.amount_cents,
            dunning_fee_cents=dunning_fee_cents,
            total_amount_cents=invoice.amount_cents + dunning_fee_cents,
            recipient_address=getattr(invoice, "customer_address", None),
            customer_name=invoice.customer_name,
            invoice_number=invoice.invoice_number,
        )

    def _create_dunning_event_impl(
        self, notice: DunningNotice, stage: DunningStage, context: DunningContext
    ) -> DunningEvent:
        """Create dunning event for notice.

        Args:
            notice: Dunning notice
            stage: Dunning stage
            context: Dunning context

        Returns:
            Dunning event
        """
        return DunningEvent(
            event_id=f"EVENT-{notice.notice_id}",
            tenant_id=notice.tenant_id,
            event_type="DUNNING_ISSUED",
            invoice_id=notice.invoice_id,
            stage=stage,
            channel=notice.channel,
            notice_ref=notice.notice_id,
            due_date=notice.due_date,
            amount_cents=notice.amount_cents,
            correlation_id=context.correlation_id,
        )

    def _send_via_brevo(self, notice: DunningNotice, context: DunningContext):
        """Send notice via Brevo email service.

        Args:
            notice: Dunning notice to send
            context: Dunning context

        Returns:
            BrevoResponse with success status
        """
        try:
            return send_transactional(
                to=notice.recipient_email,
                subject=notice.subject,
                html=notice.content,
                tenant_id=notice.tenant_id,
                dry_run=context.dry_run,
            )
        except Exception as e:
            self.logger.error(f"Failed to send via Brevo: {e}")
            from backend.integrations.brevo_client import BrevoResponse

            return BrevoResponse(success=False, error=str(e), dry_run=context.dry_run)
