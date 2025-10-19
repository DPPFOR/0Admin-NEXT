MCP Contracts (Draft 2020-12)

- All JSON Schemas declare `$schema` = `https://json-schema.org/draft/2020-12/schema`.
- Semantic Versioning strictly `MAJOR.MINOR.PATCH` (no pre-release/build suffixes).
- Allowed error codes set: {VALIDATION, NOT_FOUND, UPSTREAM, POLICY_DENIED, RETRYABLE_IO}.
- `$id` convention: `urn:0admin:mcp:<namespace.tool>:<version>:<type>` with `type` ∈ {input, output, errors}.
- `$defs` centralized within each schema; only `$ref` allowed are `#/$defs/uuid`, `#/$defs/base64`, `#/$defs/rfc3339`, `#/$defs/iso_duration`.
- UUID fields: via `$ref: #/$defs/uuid` (type string, format `uuid`, strict RFC4122 pattern).
- ISO-8601 duration (window): via `$ref: #/$defs/iso_duration` (conservative regex; months/years excluded).
- Cursors: `cursor`, `next_cursor` via `$ref: #/$defs/base64` (standard Base64; padding `=` allowed).
- etl.inbox_extract `remote_url` must start with `https://`.
- RFC3339 timestamps for `ts` (contains `Z` or offset).
- Each version folder must contain `CHANGELOG.md` starting with `1.0.0 – initial`.
