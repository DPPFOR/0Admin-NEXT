"""Tests for Flock integration - offline.

Tests the Flock-based workflow orchestration
without external dependencies.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from agents.mahnwesen.config import DunningConfig
from agents.mahnwesen.dto import DunningChannel, DunningStage
from agents.mahnwesen.playbooks import DunningContext, DunningPlaybook
from agents.mahnwesen.policies import OverdueInvoice


class TestFlockIntegration:
    """Test Flock-based workflow integration."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return DunningConfig(
            tenant_id="00000000-0000-0000-0000-000000000001",
            stage_1_threshold=3,
            stage_2_threshold=14,
            stage_3_threshold=30,
            min_amount_cents=100,
            grace_days=0,
        )

    @pytest.fixture
    def context(self, config):
        """Create test context."""
        return DunningContext(
            tenant_id=config.tenant_id, correlation_id="TEST-CORR-001", dry_run=True, limit=10
        )

    @pytest.fixture
    def playbook(self, config):
        """Create test playbook."""
        return DunningPlaybook(config)

    @pytest.fixture
    def sample_invoices(self):
        """Create sample overdue invoices."""
        now = datetime.now(UTC)
        return [
            OverdueInvoice(
                invoice_id="INV-001",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-001",
                due_date=now - timedelta(days=5),
                amount_cents=15000,
                customer_email="customer1@example.com",
                customer_name="Customer 1",
            ),
            OverdueInvoice(
                invoice_id="INV-002",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-002",
                due_date=now - timedelta(days=20),
                amount_cents=25000,
                customer_email="customer2@example.com",
                customer_name="Customer 2",
            ),
            OverdueInvoice(
                invoice_id="INV-003",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-003",
                due_date=now - timedelta(days=35),
                amount_cents=35000,
                customer_email="customer3@example.com",
                customer_name="Customer 3",
            ),
        ]

    def test_flock_flow_creation(self, playbook, context):
        """Test Flock flow creation."""
        flow = playbook.create_flow(context)

        # Check flow properties
        assert flow.name == "dunning_processing"
        assert flow.description == "Automated dunning process for overdue invoices"
        assert hasattr(flow, "add_task")

    def test_scan_overdue_invoices_task(self, playbook, context, sample_invoices):
        """Test scan overdue invoices task."""
        # Mock read client
        with patch.object(context.read_client, "get_overdue_invoices") as mock_get:
            mock_get.return_value = Mock(
                invoices=sample_invoices,
                next_cursor=None,
                total_count=len(sample_invoices),
                has_more=False,
            )

            result = playbook._scan_overdue_invoices(context)

            # Check result structure
            assert "total_found" in result
            assert "eligible_count" in result
            assert "stage_1_count" in result
            assert "stage_2_count" in result
            assert "stage_3_count" in result
            assert "invoices" in result
            assert "stage_groups" in result

            # Check counts
            assert result["total_found"] == len(sample_invoices)
            assert result["eligible_count"] == len(sample_invoices)
            assert result["stage_1_count"] == 1
            assert result["stage_2_count"] == 1
            assert result["stage_3_count"] == 1

    def test_compose_dunning_notices_task(self, playbook, context, sample_invoices):
        """Test compose dunning notices task."""
        # Setup context with scan results
        context.kwargs = {
            "scan_results": {
                "stage_groups": {
                    DunningStage.STAGE_1: [sample_invoices[0]],
                    DunningStage.STAGE_2: [sample_invoices[1]],
                    DunningStage.STAGE_3: [sample_invoices[2]],
                }
            }
        }

        result = playbook._compose_dunning_notices(context)

        # Check result structure
        assert "notices_created" in result
        assert "notices" in result

        # Check notice creation
        assert result["notices_created"] == 3
        assert len(result["notices"]) == 3

        # Check notice properties
        for notice in result["notices"]:
            assert notice.tenant_id == context.tenant_id
            assert notice.invoice_id in ["INV-001", "INV-002", "INV-003"]
            assert notice.stage in [
                DunningStage.STAGE_1,
                DunningStage.STAGE_2,
                DunningStage.STAGE_3,
            ]
            assert notice.content  # Should have rendered content
            assert notice.subject  # Should have subject

    def test_dispatch_dunning_events_task(self, playbook, context):
        """Test dispatch dunning events task."""
        from agents.mahnwesen.dto import DunningNotice

        # Create sample notices
        notices = [
            DunningNotice(
                notice_id="NOTICE-001",
                tenant_id=context.tenant_id,
                invoice_id="INV-001",
                stage=DunningStage.STAGE_1,
                channel=DunningChannel.EMAIL,
                amount_cents=15000,
                dunning_fee_cents=250,
                total_amount_cents=15250,
            ),
            DunningNotice(
                notice_id="NOTICE-002",
                tenant_id=context.tenant_id,
                invoice_id="INV-002",
                stage=DunningStage.STAGE_2,
                channel=DunningChannel.EMAIL,
                amount_cents=25000,
                dunning_fee_cents=500,
                total_amount_cents=25500,
            ),
        ]

        # Setup context with compose results
        context.kwargs = {"compose_results": {"notices": notices}}

        # Mock outbox client
        with patch.object(context.outbox_client, "check_duplicate_event", return_value=False):
            with patch.object(context.outbox_client, "publish_dunning_issued", return_value=True):
                result = playbook._dispatch_dunning_events(context)

                # Check result structure
                assert "events_dispatched" in result
                assert "total_events" in result

                # Check dispatch results
                assert result["total_events"] == 2
                assert result["events_dispatched"] == 2

    def test_dispatch_with_duplicates(self, playbook, context):
        """Test dispatch with duplicate events."""
        from agents.mahnwesen.dto import DunningNotice

        # Create sample notice
        notice = DunningNotice(
            notice_id="NOTICE-001",
            tenant_id=context.tenant_id,
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            amount_cents=15000,
        )

        # Setup context with compose results
        context.kwargs = {"compose_results": {"notices": [notice]}}

        # Mock duplicate check
        with patch.object(context.outbox_client, "check_duplicate_event", return_value=True):
            result = playbook._dispatch_dunning_events(context)

            # Should skip duplicate events
            assert result["total_events"] == 1
            assert result["events_dispatched"] == 0

    def test_dispatch_with_failures(self, playbook, context):
        """Test dispatch with publishing failures."""
        from agents.mahnwesen.dto import DunningNotice

        # Create sample notice
        notice = DunningNotice(
            notice_id="NOTICE-001",
            tenant_id=context.tenant_id,
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            amount_cents=15000,
        )

        # Setup context with compose results
        context.kwargs = {"compose_results": {"notices": [notice]}}

        # Mock publishing failure
        with patch.object(context.outbox_client, "check_duplicate_event", return_value=False):
            with patch.object(context.outbox_client, "publish_dunning_issued", return_value=False):
                result = playbook._dispatch_dunning_events(context)

                # Should report failure
                assert result["total_events"] == 1
                # In dry-run mode, events are counted as dispatched but not actually sent
                assert result["events_dispatched"] == 1

    def test_create_notice(self, playbook, context, sample_invoices):
        """Test notice creation from invoice."""
        invoice = sample_invoices[0]  # Stage 1 invoice
        stage = DunningStage.STAGE_1

        notice = playbook._create_notice(invoice, stage, context)

        # Check notice properties
        assert notice.tenant_id == invoice.tenant_id
        assert notice.invoice_id == invoice.invoice_id
        assert notice.stage == stage
        assert notice.recipient_email == invoice.customer_email
        assert notice.recipient_name == invoice.customer_name
        assert notice.amount_cents == invoice.amount_cents
        assert notice.dunning_fee_cents == 250  # Stage 1 fee
        assert notice.total_amount_cents == invoice.amount_cents + 250

    def test_create_dunning_event(self, playbook, context):
        """Test dunning event creation from notice."""
        from agents.mahnwesen.dto import DunningNotice

        notice = DunningNotice(
            notice_id="NOTICE-001",
            tenant_id=context.tenant_id,
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            notice_ref="NOTICE-001",
            due_date=datetime.now(UTC) - timedelta(days=5),
            amount_cents=15000,
        )

        event = playbook._create_dunning_event(notice, context)

        # Check event properties
        assert event.tenant_id == notice.tenant_id
        assert event.event_type == "DUNNING_ISSUED"
        assert event.invoice_id == notice.invoice_id
        assert event.stage == notice.stage
        assert event.channel == notice.channel
        assert event.notice_ref == notice.notice_ref
        assert event.amount_cents == notice.amount_cents
        assert event.correlation_id == context.correlation_id
        assert event.schema_version == "v1"

    def test_run_once_success(self, playbook, context, sample_invoices):
        """Test successful run_once execution."""
        # Mock all dependencies
        with patch.object(context.read_client, "get_overdue_invoices") as mock_get:
            mock_get.return_value = Mock(
                invoices=sample_invoices,
                next_cursor=None,
                total_count=len(sample_invoices),
                has_more=False,
            )

            with patch.object(context.outbox_client, "check_duplicate_event", return_value=False):
                with patch.object(
                    context.outbox_client, "publish_dunning_issued", return_value=True
                ):
                    result = playbook.run_once(context)

                    # Check result
                    assert result.success is True
                    assert result.notices_created == 3
                    assert result.events_dispatched == 3
                    assert result.processing_time_seconds > 0
                    assert len(result.errors) == 0

    def test_run_once_failure(self, playbook, context):
        """Test run_once execution failure."""
        # Mock API failure
        with patch.object(
            context.read_client, "get_overdue_invoices", side_effect=Exception("API Error")
        ):
            result = playbook.run_once(context)

            # Check result
            assert result.success is False
            assert len(result.errors) > 0
            assert "API Error" in result.errors[0]

    def test_dry_run_mode(self, playbook, context, sample_invoices):
        """Test dry run mode."""
        context.dry_run = True

        # Mock dependencies
        with patch.object(context.read_client, "get_overdue_invoices") as mock_get:
            mock_get.return_value = Mock(
                invoices=sample_invoices,
                next_cursor=None,
                total_count=len(sample_invoices),
                has_more=False,
            )

            result = playbook.run_once(context)

            # Should succeed in dry run mode
            assert result.success is True
            assert result.notices_created == 3
            # In dry run, events are counted as dispatched but not actually sent
            assert result.events_dispatched == 3

    def test_template_engine_integration(self, context):
        """Test template engine integration."""
        from agents.mahnwesen.dto import DunningNotice

        notice = DunningNotice(
            notice_id="NOTICE-001",
            tenant_id=context.tenant_id,
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            amount_cents=15000,
            dunning_fee_cents=250,
            total_amount_cents=15250,
        )

        # Test template rendering
        rendered = context.template_engine.render_notice(notice, DunningStage.STAGE_1)

        # Check rendered content
        assert rendered.content
        assert rendered.subject
        assert "Zahlungserinnerung" in rendered.content
        assert notice.invoice_id in rendered.content
        assert "150.00" in rendered.content

    def test_context_initialization(self, config):
        """Test context initialization."""
        context = DunningContext(
            tenant_id=config.tenant_id, correlation_id="TEST-CORR-001", dry_run=True, limit=50
        )

        # Check context properties
        assert context.tenant_id == config.tenant_id
        assert context.correlation_id == "TEST-CORR-001"
        assert context.dry_run is True
        assert context.limit == 50
        assert context.config is not None
        assert context.policies is not None
        assert context.read_client is not None
        assert context.outbox_client is not None
        assert context.template_engine is not None

    def test_workflow_trace(self, playbook, context, sample_invoices):
        """Test workflow trace and observability."""
        # Mock dependencies
        with patch.object(context.read_client, "get_overdue_invoices") as mock_get:
            mock_get.return_value = Mock(
                invoices=sample_invoices,
                next_cursor=None,
                total_count=len(sample_invoices),
                has_more=False,
            )

            with patch.object(context.outbox_client, "check_duplicate_event", return_value=False):
                with patch.object(
                    context.outbox_client, "publish_dunning_issued", return_value=True
                ):
                    result = playbook.run_once(context)

                    # Check trace information
                    assert result.success is True
                    assert result.processing_time_seconds > 0
                    assert result.notices_created > 0
                    assert result.events_dispatched > 0

    def test_error_handling(self, playbook, context):
        """Test error handling in workflow."""
        # Mock API error
        with patch.object(
            context.read_client, "get_overdue_invoices", side_effect=Exception("Network error")
        ):
            result = playbook.run_once(context)

            # Should handle error gracefully
            assert result.success is False
            assert len(result.errors) > 0
            assert "Network error" in result.errors[0]

    def test_limit_handling(self, playbook, context):
        """Test limit handling in workflow."""
        context.limit = 2

        # Create more invoices than limit
        many_invoices = [
            OverdueInvoice(
                invoice_id=f"INV-{i:03d}",
                tenant_id=context.tenant_id,
                invoice_number=f"2024-{i:03d}",
                due_date=datetime.now(UTC) - timedelta(days=5),
                amount_cents=15000,
            )
            for i in range(5)
        ]

        # Mock API with limit
        with patch.object(context.read_client, "get_overdue_invoices") as mock_get:
            mock_get.return_value = Mock(
                invoices=many_invoices[: context.limit],
                next_cursor="next-cursor",
                total_count=len(many_invoices),
                has_more=True,
            )

            with patch.object(context.outbox_client, "check_duplicate_event", return_value=False):
                with patch.object(
                    context.outbox_client, "publish_dunning_issued", return_value=True
                ):
                    result = playbook.run_once(context)

                    # Should respect limit
                    assert result.success is True
                    assert result.notices_created == context.limit
                    assert result.events_dispatched == context.limit
