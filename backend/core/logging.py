"""Centralized logging configuration with PII redaction."""

import logging
import re
from typing import Any, Dict, List, Optional


class PIIRedactionFilter(logging.Filter):
    """Filter to redact PII from log messages."""
    
    def __init__(self):
        super().__init__()
        # IBAN pattern: 2 letters + 2 digits + up to 30 alphanumeric characters
        self.iban_pattern = re.compile(r'([A-Z]{2}\d{2}[A-Z0-9]{1,30})')
        # Email pattern: word characters, @, word characters, ., word characters
        self.email_pattern = re.compile(r'(\b\S+@\S+\.\S+\b)')
        # Phone pattern: optional +, digits, spaces, dashes, slashes
        self.phone_pattern = re.compile(r'(\+?\d[\d \-/]{6,})')
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Redact PII from log record message."""
        if hasattr(record, 'msg') and record.msg:
            # Redact IBANs
            record.msg = self.iban_pattern.sub(self._mask_iban, str(record.msg))
            # Redact emails
            record.msg = self.email_pattern.sub(self._mask_email, str(record.msg))
            # Redact phone numbers
            record.msg = self.phone_pattern.sub(self._mask_phone, str(record.msg))
        
        # Also redact args if they contain strings
        if hasattr(record, 'args') and record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    arg = self.iban_pattern.sub(self._mask_iban, arg)
                    arg = self.email_pattern.sub(self._mask_email, arg)
                    arg = self.phone_pattern.sub(self._mask_phone, arg)
                new_args.append(arg)
            record.args = tuple(new_args)
        
        return True
    
    def _mask_iban(self, match) -> str:
        """Mask IBAN: show first 2 chars, mask the rest."""
        iban = match.group(1)
        if len(iban) <= 4:
            return "**" + "*" * (len(iban) - 2)
        return iban[:2] + "**" + "*" * (len(iban) - 4)
    
    def _mask_email(self, match) -> str:
        """Mask email: show first char of user, mask domain."""
        email = match.group(1)
        if "@" not in email:
            return email
        user, domain = email.split("@", 1)
        if len(user) <= 1:
            masked_user = "*"
        else:
            masked_user = user[0] + "*" * (len(user) - 1)
        return f"{masked_user}@{domain}"
    
    def _mask_phone(self, match) -> str:
        """Mask phone: show first 2 chars, mask the rest."""
        phone = match.group(1)
        if len(phone) <= 2:
            return "*" * len(phone)
        return phone[:2] + "*" * (len(phone) - 2)


def setup_logging_with_pii_redaction() -> None:
    """Setup logging with PII redaction filter."""
    # Get root logger
    root_logger = logging.getLogger()
    
    # Add PII redaction filter to all handlers
    pii_filter = PIIRedactionFilter()
    
    for handler in root_logger.handlers:
        handler.addFilter(pii_filter)
    
    # Also add to any existing loggers
    for logger_name in ['backend', 'inbox', 'importer', 'audit']:
        logger = logging.getLogger(logger_name)
        logger.addFilter(pii_filter)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with PII redaction applied."""
    logger = logging.getLogger(name)
    # Ensure PII filter is applied
    if not any(isinstance(f, PIIRedactionFilter) for f in logger.filters):
        logger.addFilter(PIIRedactionFilter())
    return logger


# Test function for PII redaction
def test_pii_redaction() -> None:
    """Test PII redaction functionality."""
    logger = get_logger("test_pii")
    
    # Test IBAN redaction
    logger.info("Processing IBAN DE89370400440532013000")
    
    # Test email redaction
    logger.info("User email: john.doe@example.com")
    
    # Test phone redaction
    logger.info("Contact: +49 30 12345678")
    
    # Test mixed content
    logger.info("User john.doe@example.com with IBAN DE89370400440532013000 and phone +49 30 12345678")


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    setup_logging_with_pii_redaction()
    
    # Test PII redaction
    test_pii_redaction()
