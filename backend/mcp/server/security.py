"""Security utilities for strict token parsing.

Token format (strict):
  Authorization: Bearer tenant:<TENANT>|role:<ROLE>
Order is free; whitespace tolerant. Malformed inputs classified as 'malformed'.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BEARER_RE = re.compile(r"^\s*Bearer\s+(?P<token>.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedToken:
    tenant: str
    role: str


class TokenError(Exception):
    kind: str

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


def parse_bearer(header_value: str | None) -> ParsedToken:
    if not header_value or not isinstance(header_value, str):
        raise TokenError("missing", "Authorization header missing")

    m = _BEARER_RE.match(header_value)
    if not m:
        raise TokenError("malformed", "Expected 'Bearer <token>'")

    token = m.group("token")
    # Split on '|' and parse key:value pairs, order-agnostic, whitespace tolerant
    parts = [p.strip() for p in token.split("|") if p.strip()]
    mapping: dict[str, str] = {}
    for p in parts:
        if ":" not in p:
            raise TokenError("malformed", "Missing ':' in token part")
        k, v = p.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if not k or not v:
            raise TokenError("malformed", "Empty key or value")
        if k not in {"tenant", "role"}:
            raise TokenError("unknown", f"Unknown token key '{k}'")
        mapping[k] = v

    if "tenant" not in mapping or "role" not in mapping:
        raise TokenError("malformed", "Required parts missing")
    # Role allowlist
    if mapping["role"] not in {"ops", "qa", "etl"}:
        raise TokenError("malformed", "Unknown role value")
    return ParsedToken(tenant=mapping["tenant"], role=mapping["role"])
