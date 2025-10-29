"""In-Memory Stammdaten-Provider für EN16931 (A1)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

from .dto import Party


@dataclass(frozen=True, slots=True)
class TenantProfile:
    tenant_id: str
    seller: Party
    payment_terms: str


class TenantProfileProvider:
    """Einfacher Provider mit optionalem Fallback auf ``TENANT_DEFAULT``."""

    def __init__(self, *, default_tenant_id: Optional[str] = None) -> None:
        self._profiles: Dict[str, TenantProfile] = {}
        self._fallback_id = default_tenant_id or os.environ.get("TENANT_DEFAULT")

    def register(self, profile: TenantProfile) -> None:
        self._profiles[profile.tenant_id] = profile

    def get(self, tenant_id: str) -> TenantProfile:
        if tenant_id in self._profiles:
            return self._profiles[tenant_id]
        if self._fallback_id and self._fallback_id in self._profiles:
            return self._profiles[self._fallback_id]
        raise KeyError(f"Tenant profile for '{tenant_id}' not found")

    def clear(self) -> None:
        self._profiles.clear()

