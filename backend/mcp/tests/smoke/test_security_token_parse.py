from __future__ import annotations

import pytest

from backend.mcp.server.security import ParsedToken, TokenError, parse_bearer


@pytest.mark.parametrize(
    "header",
    [
        "Bearer tenant:ACME|role:ops",
        "Bearer role:ops|tenant:ACME",
        "  Bearer   tenant:ACME | role:ops  ",
    ],
)
def test_token_parse_accepts_valid(header):
    token = parse_bearer(header)
    assert isinstance(token, ParsedToken)
    assert token.tenant == "ACME"
    assert token.role == "ops"


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer foo",
        "Bearer tenant:|role:ops",
        "Bearer tenant:ACME|role:",
        "Bearer tenant:ACME|unknown:ops",
        "Bearer tenant:ACME|role:admin",
        "Basic abc",
    ],
)
def test_token_parse_rejects_invalid(header):
    with pytest.raises(TokenError) as ei:
        parse_bearer(header)  # type: ignore[arg-type]
    assert ei.value.kind in {"missing", "malformed", "unknown"}
