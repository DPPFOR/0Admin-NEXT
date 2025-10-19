"""JSON structured logging with mandatory fields."""
import json
import logging
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
    """JSON formatter with mandatory fields."""

    def format(self, record):
        """Format log record as JSON with mandatory fields."""
        # Get context values or defaults
        trace_id = getattr(_context, 'trace_id', None) or 'unknown'
        tenant_id = getattr(_context, 'tenant_id', 'unknown')
        request_id = getattr(_context, 'request_id', None)

        # Build mandatory fields
        log_entry = {
            'trace_id': trace_id,
            'tenant_id': tenant_id,
            'level': record.levelname.lower(),
            'msg': record.getMessage(),
            'ts_utc': datetime.utcnow().isoformat() + 'Z'
        }

        # Add request_id if present
        if request_id:
            log_entry['request_id'] = request_id

        # Add exception info if present
        if record.exc_info:
            log_entry['exc_info'] = self.formatException(record.exc_info)

        # Add extra fields from record if any
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno',
                         'pathname', 'filename', 'module', 'exc_info',
                         'exc_text', 'stack_info', 'lineno', 'funcName',
                         'created', 'msecs', 'relativeCreated', 'thread',
                         'threadName', 'processName', 'process', 'message'):
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
