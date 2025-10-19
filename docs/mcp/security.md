MCP Security (Local)

- Token format (strict): `Bearer tenant:<TENANT>|role:<ROLE>`.
- Order is free; whitespace tolerant; unknown/missing/malformed rejected.
- No secrets at rest; redact sensitive values if printed.

Roles allowlist: `ops`, `qa`, `etl`. Unknown role values are rejected.
