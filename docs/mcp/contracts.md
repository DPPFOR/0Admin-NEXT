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

Tool-IDs (1.0.0) und Kurzbeschreibung:
- detect.mime – MIME/Typ-Erkennung (lokale Pfade unter `artifacts/inbox/`).
- archive.unpack – Entpack-Plan (Ziel bleibt in `artifacts/inbox/`).
- email.gmail.fetch – .eml Samples + Anhänge Plan.
- email.outlook.fetch – .msg Samples + Anhänge Plan.
- office.word.normalize – .docx → MD/Plain Artefakte.
- office.powerpoint.normalize – .pptx → MD/JSON Report.
- office.excel.normalize – .xlsx/.xlsb → CSV/Schema-Report (Spalten snake_case).
- pdf.text_extract – Text/Metadaten aus born-digital PDFs.
- pdf.ocr_extract – OCR-Plan (dry-run, lokaler Pfad).
- pdf.tables_extract – Tabellen als strukturierte Tabellen (leer erlaubt).
- images.ocr – OCR für PNG/JPG, einfache Box-Hinweise optional.
- data_quality.tables.validate – Tabellenvalidierung (Frictionless/Pandera-Konzept).
- security.pii.redact – PII-Erkennung/Maskierung.
