MCP Flows (Local, Read-Only)

- Inbox Local Flow chains adapters:
  detect.mime → archive.unpack → office/pdf/images.* → pdf.tables_extract → data_quality.tables.validate → security.pii.redact
- Inputs: tenant_id, path (artifacts/inbox/*), optional trace_id, flags --enable-ocr/--enable-browser (markers only).
- Output: JSON report saved under artifacts/inbox_local/<timestamp>_<sha256>_result.json.

