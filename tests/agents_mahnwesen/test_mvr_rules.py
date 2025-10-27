"""Tests for MVR rules and stage determination."""

from datetime import UTC, datetime, timedelta

import pytest

from agents.mahnwesen.config import DunningConfig
from agents.mahnwesen.mvr import DunningStage, MVREngine, OverdueInvoice


@pytest.fixture
def test_config():
    """Test configuration."""
    return DunningConfig(
        tenant_id="test-tenant",
        stage_1_threshold=14,
        stage_2_threshold=30,
        stage_3_threshold=60,
        min_amount_cents=1000,  # 10 EUR
        grace_days=3,
        max_notices_per_hour=10,
    )


@pytest.fixture
def mvr_engine(test_config):
    """MVR engine for testing."""
    return MVREngine(test_config)


@pytest.fixture
def sample_invoice():
    """Sample overdue invoice."""
    return OverdueInvoice(
        invoice_id="INV-001",
        tenant_id="test-tenant",
        customer_id="CUST-001",
        customer_name="Test Customer",
        customer_email="test@example.com",
        amount_cents=5000,  # 50 EUR
        due_date=datetime.now(UTC) - timedelta(days=20),
        invoice_number="INV-001",
        created_at=datetime.now(UTC) - timedelta(days=25),
    )


class TestMVRRules:
    """Test MVR rule engine."""

    def test_determine_stage_within_grace_period(self, mvr_engine, sample_invoice):
        """Test stage determination within grace period."""
        # Invoice due 1 day ago (within grace period)
        sample_invoice.due_date = datetime.now(UTC) - timedelta(days=1)

        stage = mvr_engine.determine_dunning_stage(sample_invoice)
        assert stage == DunningStage.STAGE_1

    def test_determine_stage_1(self, mvr_engine, sample_invoice):
        """Test stage 1 determination."""
        # Invoice due 10 days ago
        sample_invoice.due_date = datetime.now(UTC) - timedelta(days=10)

        stage = mvr_engine.determine_dunning_stage(sample_invoice)
        assert stage == DunningStage.STAGE_1

    def test_determine_stage_2(self, mvr_engine, sample_invoice):
        """Test stage 2 determination."""
        # Invoice due 20 days ago
        sample_invoice.due_date = datetime.now(UTC) - timedelta(days=20)

        stage = mvr_engine.determine_dunning_stage(sample_invoice)
        assert stage == DunningStage.STAGE_2

    def test_determine_stage_3(self, mvr_engine, sample_invoice):
        """Test stage 3 determination."""
        # Invoice due 40 days ago
        sample_invoice.due_date = datetime.now(UTC) - timedelta(days=40)

        stage = mvr_engine.determine_dunning_stage(sample_invoice)
        assert stage == DunningStage.STAGE_3

    def test_should_send_minimum_amount(self, mvr_engine, sample_invoice):
        """Test minimum amount threshold."""
        # Set amount below minimum
        sample_invoice.amount_cents = 500  # 5 EUR (below 10 EUR minimum)

        decision = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)
        assert not decision.should_send
        assert "Amount" in decision.reason
        assert decision.rate_limit_ok

    def test_should_send_stop_listed(self, mvr_engine, sample_invoice, test_config):
        """Test stop list filtering."""
        # Add stop list pattern
        test_config.stop_list_patterns = ["TEST-.*"]
        sample_invoice.invoice_number = "TEST-001"

        decision = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)
        assert not decision.should_send
        assert "stop-listed" in decision.reason

    def test_should_send_rate_limit(self, mvr_engine, sample_invoice):
        """Test rate limiting."""
        # Exhaust rate limit
        for i in range(10):  # Max 10 per hour
            mvr_engine._check_rate_limit("test-tenant")

        decision = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)
        assert not decision.should_send
        assert "Rate limit" in decision.reason
        assert not decision.rate_limit_ok

    def test_should_send_recent_dunning(self, mvr_engine, sample_invoice):
        """Test recent dunning check."""
        # Set last dunning sent recently
        sample_invoice.last_dunning_sent = datetime.now(UTC) - timedelta(hours=12)

        decision = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)
        assert not decision.should_send
        assert "already sent" in decision.reason

    def test_should_send_success(self, mvr_engine, sample_invoice):
        """Test successful dunning decision."""
        decision = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)
        assert decision.should_send
        assert decision.reason == "All checks passed"
        assert decision.rate_limit_ok
        assert decision.idempotency_key is not None

    def test_idempotency_key_deterministic(self, mvr_engine, sample_invoice):
        """Test that idempotency keys are deterministic."""
        decision1 = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)
        decision2 = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)

        assert decision1.idempotency_key == decision2.idempotency_key

    def test_idempotency_key_different_stages(self, mvr_engine, sample_invoice):
        """Test that different stages produce different keys."""
        decision1 = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_1)
        decision2 = mvr_engine.should_send_dunning(sample_invoice, DunningStage.STAGE_2)

        assert decision1.idempotency_key != decision2.idempotency_key

    def test_process_invoices(self, mvr_engine, sample_invoice):
        """Test processing multiple invoices."""
        invoices = [sample_invoice]

        results = mvr_engine.process_invoices(invoices, dry_run=False)

        assert DunningStage.STAGE_2 in results
        assert len(results[DunningStage.STAGE_2]) == 1

        invoice, decision = results[DunningStage.STAGE_2][0]
        assert invoice.invoice_id == "INV-001"
        assert decision.should_send

    def test_rate_limit_status(self, mvr_engine):
        """Test rate limit status reporting."""
        status = mvr_engine.get_rate_limit_status("test-tenant")

        assert status["current_count"] == 0
        assert status["max_per_hour"] == 10
        assert status["remaining"] == 10

    def test_reset_rate_limits(self, mvr_engine):
        """Test rate limit reset."""
        # Add some rate limit entries
        mvr_engine._check_rate_limit("test-tenant")
        mvr_engine._check_rate_limit("test-tenant")

        status_before = mvr_engine.get_rate_limit_status("test-tenant")
        assert status_before["current_count"] == 2

        # Reset
        mvr_engine.reset_rate_limits("test-tenant")

        status_after = mvr_engine.get_rate_limit_status("test-tenant")
        assert status_after["current_count"] == 0
