"""JSON structured logging with mandatory fields and PII redaction."""
import json
import logging
import re
import sys
from datetime import datetime
from typing import Optional

from backend.core.config import settings
import hmac
from hashlib import sha256

# Thread-local storage for context
import threading
_context = threading.local()


class JSONFormatter(logging.Formatter):
    """JSON formatter with mandatory fields and PII redaction."""

    def __init__(self):
        super().__init__()
        # PII patterns
        self.iban_pattern = re.compile(r'([A-Z]{2}\d{2}[A-Z0-9]{1,30})')
        self.email_pattern = re.compile(r'(\b\S+@\S+\.\S+\b)')
        self.phone_pattern = re.compile(r'(\+?\d[\d \-/]{6,})')

    def _redact_pii(self, text: str) -> str:
        """Redact PII from text."""
        if not isinstance(text, str):
            return text
        
        # Redact IBANs
        text = self.iban_pattern.sub(self._mask_iban, text)
        # Redact emails
        text = self.email_pattern.sub(self._mask_email, text)
        # Redact phone numbers
        text = self.phone_pattern.sub(self._mask_phone, text)
        
        return text

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

    def format(self, record):
        """Format log record as JSON with mandatory fields and PII redaction."""
        # Get context values or defaults
        trace_id = getattr(_context, 'trace_id', None) or 'unknown'
        tenant_id = getattr(_context, 'tenant_id', 'unknown')
        request_id = getattr(_context, 'request_id', None)

        # Get message and redact PII
        message = record.getMessage()
        redacted_message = self._redact_pii(message)

        # Build mandatory fields
        log_entry = {
            'trace_id': trace_id,
            'tenant_id': tenant_id,
            'level': record.levelname.lower(),
            'msg': redacted_message,
            'ts_utc': datetime.utcnow().isoformat() + 'Z'
        }

        # Add request_id if present
        if request_id:
            log_entry['request_id'] = request_id

        # Add exception info if present
        if record.exc_info:
            log_entry['exc_info'] = self.formatException(record.exc_info)

        # Add extra fields from record if any (with PII redaction)
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno',
                         'pathname', 'filename', 'module', 'exc_info',
                         'exc_text', 'stack_info', 'lineno', 'funcName',
                         'created', 'msecs', 'relativeCreated', 'thread',
                         'threadName', 'processName', 'process', 'message'):
                # Redact PII from string values
                if isinstance(value, str):
                    value = self._redact_pii(value)
                log_entry[key] = value

        return json.dumps(log_entry)


def set_trace_id(trace_id: str) -> None:
    """Set trace ID for current thread context."""
    _context.trace_id = trace_id


def set_tenant_id(tenant_id: str) -> None:
    """Set tenant ID for current thread context."""
    _context.tenant_id = tenant_id


def set_request_id(request_id: Optional[str]) -> None:
    """Set request ID for current thread context."""
    _context.request_id = request_id


def init_logging() -> None:
    """Initialize JSON logging with mandatory fields."""
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get logger with JSON formatting."""
    return logging.getLogger(name)


# Convenience logger
logger = get_logger(__name__)


def hash_actor_token(token: str) -> str:
    """Return an HMAC-SHA256 hash of a sensitive token using CURSOR_HMAC_KEY.

    The raw token must never be logged. This helper produces a stable hash for
    audit purposes without exposing the original value. CURSOR_HMAC_KEY should
    be a strong secret (>=32 bytes) and rotated regularly (dual-key phase
    recommended, documented in runbooks).
    """
    key = settings.CURSOR_HMAC_KEY.encode()
    return hmac.new(key, token.encode(), sha256).hexdigest()
