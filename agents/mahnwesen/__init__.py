"""Mahnwesen Agent - Flock-based dunning management system.

This module provides the core functionality for automated dunning processes
using the Flock framework. It handles overdue invoice detection, dunning
stage determination, notice composition, and event dispatch.

Key Components:
- Config: Configuration management with tenant-specific settings
- Policies: Business rules for dunning stage determination
- DTOs: Data transfer objects for type safety
- Clients: Read-API and Outbox integration
- Playbooks: Flock-based workflow orchestration
- Templates: Jinja2-based notice templates

Multi-tenant support with strict tenant isolation via RLS.
"""

__version__ = "1.0.0"
__author__ = "0Admin-NEXT Team"

from .clients import OutboxClient, ReadApiClient
from .config import DunningConfig
from .dto import (
    DunningChannel,
    DunningEvent,
    DunningNotice,
    DunningStage,
    OverdueInvoice,
)
from .playbooks import DunningPlaybook
from .policies import DunningPolicies

__all__ = [
    "DunningConfig",
    "DunningPolicies",
    "OverdueInvoice",
    "DunningNotice",
    "DunningEvent",
    "DunningStage",
    "DunningChannel",
    "ReadApiClient",
    "OutboxClient",
    "DunningPlaybook",
]
