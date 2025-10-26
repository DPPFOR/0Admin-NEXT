"""Tests for overdue invoice rules - offline.

Tests the business logic for determining dunning stages
without external dependencies.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from agents.mahnwesen.config import DunningConfig
from agents.mahnwesen.policies import DunningPolicies, OverdueInvoice
from agents.mahnwesen.dto import DunningStage, DunningChannel


class TestOverdueRules:
    """Test overdue invoice business rules."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return DunningConfig(
            tenant_id="00000000-0000-0000-0000-000000000001",
            stage_1_threshold=3,
            stage_2_threshold=14,
            stage_3_threshold=30,
            min_amount_cents=100,
            grace_days=0
        )
    
    @pytest.fixture
    def policies(self, config):
        """Create test policies."""
        return DunningPolicies(config)
    
    @pytest.fixture
    def now(self):
        """Get current timestamp for testing."""
        return datetime.now(timezone.utc)
    
    @pytest.fixture
    def sample_invoice(self, now):
        """Create sample overdue invoice."""
        return OverdueInvoice(
            invoice_id="INV-001",
            tenant_id="00000000-0000-0000-0000-000000000001",
            invoice_number="2024-001",
            due_date=now - timedelta(days=5),
            amount_cents=15000,  # 150.00 EUR
            customer_email="customer@example.com",
            customer_name="Test Customer"
        )
    
    def test_stage_1_threshold(self, policies, sample_invoice, now):
        """Test stage 1 threshold determination."""
        # Invoice overdue for 5 days (stage 1 threshold is 3)
        invoice = sample_invoice
        invoice.due_date = now - timedelta(days=5)
        
        stage = policies.determine_dunning_stage(invoice, now)
        assert stage == DunningStage.STAGE_1
    
    def test_stage_2_threshold(self, policies, sample_invoice, now):
        """Test stage 2 threshold determination."""
        # Invoice overdue for 20 days (stage 2 threshold is 14)
        invoice = sample_invoice
        invoice.due_date = now - timedelta(days=20)
        
        stage = policies.determine_dunning_stage(invoice, now)
        assert stage == DunningStage.STAGE_2
    
    def test_stage_3_threshold(self, policies, sample_invoice, now):
        """Test stage 3 threshold determination."""
        # Invoice overdue for 35 days (stage 3 threshold is 30)
        invoice = sample_invoice
        invoice.due_date = now - timedelta(days=35)
        
        stage = policies.determine_dunning_stage(invoice, now)
        assert stage == DunningStage.STAGE_3
    
    def test_no_dunning_before_threshold(self, policies, sample_invoice, now):
        """Test no dunning before stage 1 threshold."""
        # Invoice overdue for 2 days (below stage 1 threshold)
        invoice = sample_invoice
        invoice.due_date = now - timedelta(days=2)
        
        stage = policies.determine_dunning_stage(invoice, now)
        assert stage == DunningStage.NONE
    
    def test_grace_period(self, config, now):
        """Test grace period handling."""
        # Configure grace period
        config.grace_days = 5
        policies = DunningPolicies(config)
        
        # Invoice overdue for 8 days, but with 5-day grace period
        # Effective overdue: 3 days (stage 1 threshold)
        invoice = OverdueInvoice(
            invoice_id="INV-002",
            tenant_id="00000000-0000-0000-0000-000000000001",
            invoice_number="2024-002",
            due_date=now - timedelta(days=8),
            amount_cents=15000
        )
        
        stage = policies.determine_dunning_stage(invoice, now)
        assert stage == DunningStage.STAGE_1
    
    def test_minimum_amount_filter(self, policies, sample_invoice, now):
        """Test minimum amount filtering."""
        # Invoice below minimum amount
        invoice = sample_invoice
        invoice.amount_cents = 50  # Below 100 cent minimum
        
        should_issue, error_msg = policies.should_issue_dunning(invoice, now)
        assert not should_issue
        assert error_msg is not None
    
    def test_stop_list_filter(self, config, policies, sample_invoice, now):
        """Test stop list filtering."""
        # Add stop list pattern
        config.stop_list_patterns = [r"TEST-.*"]
        
        # Invoice matching stop list pattern
        invoice = sample_invoice
        invoice.invoice_number = "TEST-001"
        
        should_issue, error_msg = policies.should_issue_dunning(invoice, now)
        assert not should_issue
        assert error_msg is not None
    
    def test_maximum_stage_filter(self, policies, sample_invoice, now):
        """Test maximum stage filtering."""
        # Invoice already at maximum stage
        invoice = sample_invoice
        invoice.dunning_stage = 3
        
        should_issue, error_msg = policies.should_issue_dunning(invoice, now)
        assert not should_issue
        assert error_msg is not None
    
    def test_recent_dunning_filter(self, policies, sample_invoice, now):
        """Test recent dunning filtering."""
        # Invoice with recent dunning (less than 1 day ago)
        invoice = sample_invoice
        invoice.last_dunning_date = now - timedelta(hours=12)
        
        should_issue, error_msg = policies.should_issue_dunning(invoice, now)
        assert not should_issue
        assert error_msg is not None
    
    def test_channel_determination_stage_1(self, policies, sample_invoice):
        """Test channel determination for stage 1."""
        invoice = sample_invoice
        stage = DunningStage.STAGE_1
        
        channel = policies.determine_dunning_channel(invoice, stage)
        assert channel == DunningChannel.EMAIL
    
    def test_channel_determination_stage_2(self, policies, sample_invoice):
        """Test channel determination for stage 2."""
        invoice = sample_invoice
        stage = DunningStage.STAGE_2
        
        channel = policies.determine_dunning_channel(invoice, stage)
        assert channel == DunningChannel.EMAIL
    
    def test_channel_determination_stage_3(self, policies, sample_invoice):
        """Test channel determination for stage 3."""
        invoice = sample_invoice
        stage = DunningStage.STAGE_3
        
        channel = policies.determine_dunning_channel(invoice, stage)
        assert channel == DunningChannel.LETTER
    
    def test_channel_determination_no_email(self, policies):
        """Test channel determination without email."""
        invoice = OverdueInvoice(
            invoice_id="INV-003",
            tenant_id="00000000-0000-0000-0000-000000000001",
            invoice_number="2024-003",
            due_date=datetime.now(timezone.utc) - timedelta(days=20),
            amount_cents=15000,
            customer_email=None  # No email
        )
        stage = DunningStage.STAGE_2
        
        channel = policies.determine_dunning_channel(invoice, stage)
        assert channel == DunningChannel.LETTER
    
    def test_dunning_fee_calculation(self, policies, sample_invoice):
        """Test dunning fee calculation."""
        # Stage 1 fee
        fee_1 = policies.calculate_dunning_fee(sample_invoice, DunningStage.STAGE_1)
        assert fee_1 == 250  # 2.50 EUR
        
        # Stage 2 fee
        fee_2 = policies.calculate_dunning_fee(sample_invoice, DunningStage.STAGE_2)
        assert fee_2 == 500  # 5.00 EUR
        
        # Stage 3 fee
        fee_3 = policies.calculate_dunning_fee(sample_invoice, DunningStage.STAGE_3)
        assert fee_3 == 1000  # 10.00 EUR
    
    def test_escalation_delay_calculation(self, policies):
        """Test escalation delay calculation."""
        # Stage 1 to Stage 2
        delay_1_2 = policies.get_escalation_delay_days(
            DunningStage.STAGE_1,
            DunningStage.STAGE_2
        )
        assert delay_1_2 == 11  # 14 - 3 = 11 days
        
        # Stage 2 to Stage 3
        delay_2_3 = policies.get_escalation_delay_days(
            DunningStage.STAGE_2,
            DunningStage.STAGE_3
        )
        assert delay_2_3 == 16  # 30 - 14 = 16 days
    
    def test_filter_overdue_invoices(self, policies, now):
        """Test filtering of overdue invoices."""
        # Create test invoices
        invoices = [
            OverdueInvoice(
                invoice_id="INV-001",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-001",
                due_date=now - timedelta(days=5),
                amount_cents=15000
            ),
            OverdueInvoice(
                invoice_id="INV-002",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-002",
                due_date=now - timedelta(days=1),
                amount_cents=50  # Below minimum
            ),
            OverdueInvoice(
                invoice_id="INV-003",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-003",
                due_date=now - timedelta(days=20),
                amount_cents=15000
            )
        ]
        
        # Filter invoices
        eligible = policies.filter_overdue_invoices(invoices, now)
        
        # Should filter out invoice below minimum amount
        assert len(eligible) == 2
        assert eligible[0].invoice_id == "INV-001"
        assert eligible[1].invoice_id == "INV-003"
    
    def test_group_by_stage(self, policies, now):
        """Test grouping invoices by stage."""
        # Create test invoices
        invoices = [
            OverdueInvoice(
                invoice_id="INV-001",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-001",
                due_date=now - timedelta(days=5),
                amount_cents=15000
            ),
            OverdueInvoice(
                invoice_id="INV-002",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-002",
                due_date=now - timedelta(days=20),
                amount_cents=15000
            ),
            OverdueInvoice(
                invoice_id="INV-003",
                tenant_id="00000000-0000-0000-0000-000000000001",
                invoice_number="2024-003",
                due_date=now - timedelta(days=35),
                amount_cents=15000
            )
        ]
        
        # Group by stage
        groups = policies.group_by_stage(invoices, now)
        
        # Check grouping
        assert len(groups[DunningStage.STAGE_1]) == 1
        assert len(groups[DunningStage.STAGE_2]) == 1
        assert len(groups[DunningStage.STAGE_3]) == 1
        
        assert groups[DunningStage.STAGE_1][0].invoice_id == "INV-001"
        assert groups[DunningStage.STAGE_2][0].invoice_id == "INV-002"
        assert groups[DunningStage.STAGE_3][0].invoice_id == "INV-003"
    
    @pytest.mark.parametrize("days_overdue,expected_stage", [
        (1, DunningStage.NONE),
        (2, DunningStage.NONE),
        (3, DunningStage.STAGE_1),
        (5, DunningStage.STAGE_1),
        (14, DunningStage.STAGE_2),
        (20, DunningStage.STAGE_2),
        (30, DunningStage.STAGE_3),
        (35, DunningStage.STAGE_3),
    ])
    def test_stage_determination_parametrized(self, policies, now, days_overdue, expected_stage):
        """Test stage determination with various overdue periods."""
        invoice = OverdueInvoice(
            invoice_id="INV-TEST",
            tenant_id="00000000-0000-0000-0000-000000000001",
            invoice_number="2024-TEST",
            due_date=now - timedelta(days=days_overdue),
            amount_cents=15000
        )
        
        stage = policies.determine_dunning_stage(invoice, now)
        assert stage == expected_stage
