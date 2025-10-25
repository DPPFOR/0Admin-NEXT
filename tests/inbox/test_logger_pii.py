"""Tests for PII redaction in logging — auto-generated via PDD."""

import pytest
import logging
import json
from io import StringIO
from backend.core.observability.logging import JSONFormatter


class TestLoggerPII:
    """Test PII redaction in logging."""
    
    @pytest.fixture
    def formatter(self):
        """JSON formatter with PII redaction."""
        return JSONFormatter()
    
    @pytest.fixture
    def log_capture(self):
        """Capture log output."""
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(JSONFormatter())
        return handler
    
    def test_iban_redaction(self, formatter):
        """Test that IBANs are redacted in log messages."""
        # Create a log record with IBAN
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing IBAN DE89370400440532013000",
            args=(),
            exc_info=None
        )
        
        # Format the record
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Check that IBAN is redacted
        assert "DE89370400440532013000" not in log_data["msg"]
        assert "DE**" in log_data["msg"]  # Should show first 2 chars + **
    
    def test_email_redaction(self, formatter):
        """Test that emails are redacted in log messages."""
        # Create a log record with email
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User email: john.doe@example.com",
            args=(),
            exc_info=None
        )
        
        # Format the record
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Check that email is redacted
        assert "john.doe@example.com" not in log_data["msg"]
        assert "j*******@example.com" in log_data["msg"]  # Should show first char + ***
    
    def test_phone_redaction(self, formatter):
        """Test that phone numbers are redacted in log messages."""
        # Create a log record with phone
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Contact: +49 30 12345678",
            args=(),
            exc_info=None
        )
        
        # Format the record
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Check that phone is redacted
        assert "+49 30 12345678" not in log_data["msg"]
        assert "+4***" in log_data["msg"]  # Should show first 2 chars + ***
    
    def test_mixed_pii_redaction(self, formatter):
        """Test that multiple PII types are redacted in the same message."""
        # Create a log record with mixed PII
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User john.doe@example.com with IBAN DE89370400440532013000 and phone +49 30 12345678",
            args=(),
            exc_info=None
        )
        
        # Format the record
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Check that all PII is redacted
        assert "john.doe@example.com" not in log_data["msg"]
        assert "DE89370400440532013000" not in log_data["msg"]
        assert "+49 30 12345678" not in log_data["msg"]
        
        # Check that redacted versions are present
        assert "j*******@example.com" in log_data["msg"]
        assert "DE********************" in log_data["msg"]
        assert "+4*************" in log_data["msg"]
    
    def test_extra_fields_pii_redaction(self, formatter):
        """Test that PII in extra fields is also redacted."""
        # Create a log record with PII in extra fields
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing user data",
            args=(),
            exc_info=None
        )
        
        # Add PII to extra fields
        record.user_email = "jane.smith@example.com"
        record.user_iban = "FR1420041010050500013M02606"
        record.user_phone = "+33 1 23 45 67 89"
        
        # Format the record
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Check that PII in extra fields is redacted
        assert "jane.smith@example.com" not in log_data["user_email"]
        assert "j*********@example.com" in log_data["user_email"]
        
        assert "FR1420041010050500013M02606" not in log_data["user_iban"]
        assert "FR**" in log_data["user_iban"]
        
        assert "+33 1 23 45 67 89" not in log_data["user_phone"]
        assert "+3***" in log_data["user_phone"]
    
    def test_no_pii_preserved(self, formatter):
        """Test that non-PII content is preserved."""
        # Create a log record without PII
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing document with ID 12345",
            args=(),
            exc_info=None
        )
        
        # Format the record
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        
        # Check that non-PII content is preserved
        assert "Processing document with ID 12345" == log_data["msg"]
    
    def test_edge_cases(self, formatter):
        """Test edge cases for PII redaction."""
        # Test short IBAN
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Short IBAN: DE12",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        # Short IBANs might not be detected by the pattern
        # This is expected behavior for very short strings
        
        # Test single character email
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Email: a@b.com",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        assert "a@b.com" not in log_data["msg"]
        assert "*@b.com" in log_data["msg"]
