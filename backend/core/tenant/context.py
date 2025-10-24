from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status

from backend.core.tenant.validator import validate_tenant
from backend.core.observability.metrics import increment_counter


async def require_tenant(tenant_header: Optional[str] = Header(None, alias="X-Tenant-ID", convert_underscores=False)) -> str:
    """FastAPI dependency to validate X-Tenant against allowlist.

    Returns tenant_id (UUID string) on success; raises HTTPException on failure.
    """
    res = validate_tenant(tenant_header)
    if not res.ok:
        increment_counter("tenant_validation_failures_total", labels={"reason": res.reason})
        code = {
            "missing": (status.HTTP_401_UNAUTHORIZED, "tenant_missing"),
            "malformed": (status.HTTP_401_UNAUTHORIZED, "tenant_malformed"),
            "unknown": (status.HTTP_403_FORBIDDEN, "tenant_unknown"),
        }[res.reason]
        raise HTTPException(status_code=code[0], detail={"error": code[1], "detail": res.reason})
    return tenant_header  # type: ignore[return-value]

