"""Inbox app module.

Provides FastAPI router for Upload API v1.
"""

from .api import router as upload_router  # re-export for app integration
from .api_read import router as read_router
from .api_ops import router as ops_router

__all__ = [
    "upload_router",
    "read_router",
    "ops_router",
]
