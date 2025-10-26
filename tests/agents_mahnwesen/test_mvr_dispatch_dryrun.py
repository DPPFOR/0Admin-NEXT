"""Tests for MVR dispatch in dry-run mode."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from agents.mahnwesen.playbooks import DunningPlaybook, DunningContext
from agents.mahnwesen.config import DunningConfig
from agents.mahnwesen.mvr import OverdueInvoice, DunningStage


@pytest.fixture
def test_config():
    """Test configuration."""
    return DunningConfig(
        tenant_id="test-tenant",
        stage_1_threshold=14,
        stage_2_threshold=30,
        stage_3_threshold=60,
        min_amount_cents=1000,
        grace_days=3,
        max_notices_per_hour=10
    )


@pytest.fixture
def sample_invoices():
    """Sample overdue invoices."""
    return [
        OverdueInvoice(
            invoice_id="INV-001",
            tenant_id="test-tenant",
            customer_id="CUST-001",
            customer_name="Test Customer 1",
            customer_email="test1@example.com",
            amount_cents=5000,
            due_date=datetime.now(timezone.utc) - timedelta(days=10),
            invoice_number="INV-001",
            created_at=datetime.now(timezone.utc) - timedelta(days=15)
        ),
        OverdueInvoice(
            invoice_id="INV-002",
            tenant_id="test-tenant",
            customer_id="CUST-002",
            customer_name="Test Customer 2",
            customer_email="test2@example.com",
            amount_cents=3000,
            due_date=datetime.now(timezone.utc) - timedelta(days=20),
            invoice_number="INV-002",
            created_at=datetime.now(timezone.utc) - timedelta(days=25)
        )
    ]


class TestMVREispatchDryRun:
    """Test MVR dispatch in dry-run mode."""
    
    @patch('agents.mahnwesen.playbooks.ReadApiClient')
    @patch('agents.mahnwesen.playbooks.OutboxClient')
    def test_dry_run_no_side_effects(self, mock_outbox, mock_read_api, test_config, sample_invoices):
        """Test that dry-run mode produces no side effects."""
        # Setup mocks
        mock_read_api.return_value.get_overdue_invoices.return_value = Mock(invoices=sample_invoices)
        mock_outbox.return_value.check_duplicate_event.return_value = False
        mock_outbox.return_value.publish_dunning_issued.return_value = True
        
        # Create context
        context = DunningContext(
            tenant_id="test-tenant",
            correlation_id="test-correlation",
            dry_run=True,
            config=test_config
        )
        
        # Create playbook
        playbook = DunningPlaybook(test_config)
        
        # Run dry-run
        result = playbook.run_once(context)
        
        # Verify results
        assert result.success
        assert result.notices_created == 2  # Both invoices processed
        # In dry-run, events are still dispatched but with dry_run=True
        assert result.events_dispatched == 2
        assert result.processing_time_seconds > 0
        
        # Verify no actual API calls were made
        mock_outbox.return_value.publish_dunning_issued.assert_not_called()
    
    @patch('agents.mahnwesen.playbooks.ReadApiClient')
    @patch('agents.mahnwesen.playbooks.OutboxClient')
    @patch('agents.mahnwesen.playbooks.send_transactional')
    def test_dry_run_brevo_simulation(self, mock_brevo, mock_outbox, mock_read_api, test_config, sample_invoices):
        """Test that dry-run mode simulates Brevo sending."""
        # Setup mocks
        mock_read_api.return_value.get_overdue_invoices.return_value = Mock(invoices=sample_invoices)
        mock_outbox.return_value.check_duplicate_event.return_value = False
        mock_brevo.return_value = Mock(success=True, dry_run=True)
        
        # Create context
        context = DunningContext(
            tenant_id="test-tenant",
            correlation_id="test-correlation",
            dry_run=True,
            config=test_config
        )
        
        # Create playbook
        playbook = DunningPlaybook(test_config)
        
        # Run dry-run
        result = playbook.run_once(context)
        
        # Verify Brevo was called in dry-run mode
        assert mock_brevo.call_count == 2  # Called for each invoice
        for call in mock_brevo.call_args_list:
            args, kwargs = call
            assert kwargs['dry_run'] is True
            assert kwargs['tenant_id'] == "test-tenant"
    
    @patch('agents.mahnwesen.playbooks.ReadApiClient')
    @patch('agents.mahnwesen.playbooks.OutboxClient')
    def test_rate_limiting_bypass_in_dry_run(self, mock_outbox, mock_read_api, test_config, sample_invoices):
        """Test that rate limiting is bypassed in dry-run mode."""
        # Setup mocks
        mock_read_api.return_value.get_overdue_invoices.return_value = Mock(invoices=sample_invoices)
        mock_outbox.return_value.check_duplicate_event.return_value = False
        
        # Create context
        context = DunningContext(
            tenant_id="test-tenant",
            correlation_id="test-correlation",
            dry_run=True,
            config=test_config
        )
        
        # Create playbook
        playbook = DunningPlaybook(test_config)
        
        # Exhaust rate limit first
        for i in range(15):  # More than max_notices_per_hour
            context.mvr_engine._check_rate_limit("test-tenant")
        
        # Run dry-run (should still work despite rate limit)
        result = playbook.run_once(context)
        
        # Verify it still processes invoices in dry-run
        assert result.success
        assert result.notices_created == 2
    
    @patch('agents.mahnwesen.playbooks.ReadApiClient')
    @patch('agents.mahnwesen.playbooks.OutboxClient')
    def test_deterministic_processing(self, mock_outbox, mock_read_api, test_config, sample_invoices):
        """Test that processing is deterministic."""
        # Setup mocks
        mock_read_api.return_value.get_overdue_invoices.return_value = Mock(invoices=sample_invoices)
        mock_outbox.return_value.check_duplicate_event.return_value = False
        
        # Create context
        context = DunningContext(
            tenant_id="test-tenant",
            correlation_id="test-correlation",
            dry_run=True,
            config=test_config
        )
        
        # Create playbook
        playbook = DunningPlaybook(test_config)
        
        # Run multiple times
        result1 = playbook.run_once(context)
        result2 = playbook.run_once(context)
        
        # Results should be identical
        assert result1.success == result2.success
        assert result1.notices_created == result2.notices_created
        assert result1.events_dispatched == result2.events_dispatched
    
    @patch('agents.mahnwesen.playbooks.ReadApiClient')
    @patch('agents.mahnwesen.playbooks.OutboxClient')
    def test_empty_invoice_list(self, mock_outbox, mock_read_api, test_config):
        """Test handling of empty invoice list."""
        # Setup mocks
        mock_read_api.return_value.get_overdue_invoices.return_value = Mock(invoices=[])
        
        # Create context
        context = DunningContext(
            tenant_id="test-tenant",
            correlation_id="test-correlation",
            dry_run=True,
            config=test_config
        )
        
        # Create playbook
        playbook = DunningPlaybook(test_config)
        
        # Run dry-run
        result = playbook.run_once(context)
        
        # Verify results
        assert result.success
        assert result.notices_created == 0
        assert result.events_dispatched == 0
        assert "No overdue invoices found" in result.warnings
    
    @patch('agents.mahnwesen.playbooks.ReadApiClient')
    @patch('agents.mahnwesen.playbooks.OutboxClient')
    def test_error_handling(self, mock_outbox, mock_read_api, test_config):
        """Test error handling in dry-run mode."""
        # Setup mocks to raise exception
        mock_read_api.return_value.get_overdue_invoices.side_effect = Exception("API Error")
        
        # Create context
        context = DunningContext(
            tenant_id="test-tenant",
            correlation_id="test-correlation",
            dry_run=True,
            config=test_config
        )
        
        # Create playbook
        playbook = DunningPlaybook(test_config)
        
        # Run dry-run
        result = playbook.run_once(context)
        
        # Verify error handling
        assert not result.success
        assert "API Error" in result.errors[0]
        assert result.processing_time_seconds > 0
