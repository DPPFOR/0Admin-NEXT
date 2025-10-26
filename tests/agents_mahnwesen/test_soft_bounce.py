"""Tests for Soft-Bounce Policy (3 attempts in 72h)."""

import pytest
from datetime import datetime, timezone, timedelta

from backend.integrations.brevo_client import BrevoClient


class TestSoftBouncePolicy:
    """Test soft-bounce policy: max 3 attempts in 72h."""
    
    def test_first_attempt_allowed(self):
        """Test that first attempt is always allowed."""
        client = BrevoClient()
        email = "test@example.com"
        
        can_retry, reason = client._check_soft_bounce_policy(email)
        
        assert can_retry
        assert reason is None
    
    def test_record_soft_bounce(self):
        """Test recording a soft-bounce."""
        client = BrevoClient()
        email = "test@example.com"
        
        client.record_soft_bounce(email)
        
        status = client.get_soft_bounce_status(email)
        assert status["attempts"] == 1
        assert status["can_retry"]
        assert "3 attempts in 72h" in status["policy"]
    
    def test_three_attempts_allowed(self):
        """Test that up to 3 attempts are allowed in 72h."""
        client = BrevoClient()
        email = "test@example.com"
        
        # Record 3 soft-bounces
        client.record_soft_bounce(email)
        client.record_soft_bounce(email)
        client.record_soft_bounce(email)
        
        status = client.get_soft_bounce_status(email)
        assert status["attempts"] == 3
        assert not status["can_retry"]  # 3rd attempt triggers policy
        assert "exceeded" in status["reason"]
    
    def test_four_attempts_blocked(self):
        """Test that 4th attempt is blocked and promotes to hard-bounce."""
        client = BrevoClient()
        email = "test@example.com"
        
        # Record 3 soft-bounces (triggers policy)
        client.record_soft_bounce(email)
        client.record_soft_bounce(email)
        client.record_soft_bounce(email)
        
        # Email should now be hard-bounced
        assert client.is_hard_bounced(email)
        
        # Status should show policy exceeded
        status = client.get_soft_bounce_status(email)
        assert not status["can_retry"]
    
    def test_old_attempts_cleaned_up(self):
        """Test that attempts older than 72h are cleaned up."""
        client = BrevoClient()
        email = "test@example.com"
        
        # Simulate old attempts (outside 72h window)
        now = datetime.now(timezone.utc)
        old_timestamp = now - timedelta(hours=73)
        client._soft_bounces[email.lower()] = [old_timestamp, old_timestamp]
        
        # Record new attempt
        client.record_soft_bounce(email)
        
        status = client.get_soft_bounce_status(email)
        assert status["attempts"] == 1  # Old attempts removed
        assert status["can_retry"]
    
    def test_policy_window_rolling(self):
        """Test that policy window is rolling (72h)."""
        client = BrevoClient()
        email = "test@example.com"
        
        now = datetime.now(timezone.utc)
        
        # Simulate 2 attempts: one old, one recent
        old_timestamp = now - timedelta(hours=73)
        recent_timestamp = now - timedelta(hours=1)
        client._soft_bounces[email.lower()] = [old_timestamp, recent_timestamp]
        
        # Check policy - only recent attempt counts
        can_retry, reason = client._check_soft_bounce_policy(email)
        assert can_retry  # Only 1 attempt in window
        
        # Record 2 more attempts
        client.record_soft_bounce(email)
        client.record_soft_bounce(email)
        
        # Now should have 3 in window (recent + 2 new)
        status = client.get_soft_bounce_status(email)
        assert status["attempts"] == 3
        assert not status["can_retry"]
    
    def test_send_blocked_after_policy_exceeded(self):
        """Test that send is blocked when soft-bounce policy is exceeded."""
        client = BrevoClient()
        email = "test@example.com"
        
        # Simulate 3 soft-bounces
        client.record_soft_bounce(email)
        client.record_soft_bounce(email)
        client.record_soft_bounce(email)
        
        # Try to send
        response = client.send_transactional(
            to=email,
            subject="Test",
            html="Test",
            tenant_id="test-tenant",
            dry_run=False
        )
        
        assert not response.success
        assert "Soft-bounce policy exceeded" in response.error or "hard-bounce" in response.error
    
    def test_different_emails_independent(self):
        """Test that soft-bounce tracking is per email."""
        client = BrevoClient()
        email1 = "test1@example.com"
        email2 = "test2@example.com"
        
        # Record bounces for email1
        client.record_soft_bounce(email1)
        client.record_soft_bounce(email1)
        client.record_soft_bounce(email1)
        
        # email2 should still be allowed
        status = client.get_soft_bounce_status(email2)
        assert status["attempts"] == 0
        assert status["can_retry"]
    
    def test_soft_bounce_status_includes_timestamps(self):
        """Test that soft-bounce status includes last attempt timestamp."""
        client = BrevoClient()
        email = "test@example.com"
        
        before = datetime.now(timezone.utc)
        client.record_soft_bounce(email)
        after = datetime.now(timezone.utc)
        
        status = client.get_soft_bounce_status(email)
        assert status["last_attempt"] is not None
        
        last_attempt = datetime.fromisoformat(status["last_attempt"])
        assert before <= last_attempt <= after

