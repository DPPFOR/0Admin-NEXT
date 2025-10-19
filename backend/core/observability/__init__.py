"""Minimal observability for logging, health checks and metrics.

Provides JSON logging, health/readiness endpoints, and in-process metrics
for go-live readiness without external dependencies.
"""
import os
import uuid
from typing import Optional

from . import logging as logging_module
from . import health
from . import metrics

# Global trace_id generator for worker/CLI contexts
def generate_trace_id() -> str:
    """Generate a new trace ID for request/worker context."""
    return str(uuid.uuid4())


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """Set or generate trace ID for current context."""
    if not trace_id:
        trace_id = generate_trace_id()
    # Store in thread-local or context variable for logging middleware
    return trace_id


def set_tenant_id(tenant_id: Optional[str] = None) -> str:
    """Set tenant ID for current context (default 'unknown')."""
    return tenant_id or "unknown"


def init_observability(enable_metrics: bool = True) -> None:
    """Initialize all observability components."""
    logging_module.init_logging()
    if enable_metrics:
        metrics.init_metrics()


__all__ = [
    "logging_module",
    "health",
    "metrics",
    "generate_trace_id",
    "set_trace_id",
    "set_tenant_id",
    "init_observability",
]
