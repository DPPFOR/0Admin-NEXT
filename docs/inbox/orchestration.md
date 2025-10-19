Inbox Orchestration (Local, Read-Only)

- How to run:
  - CLI: `python tools/flows/run_inbox_local_flow.py --tenant 00000000-0000-0000-0000-000000000001 --path artifacts/inbox/samples/pdf/sample.pdf`
  - Flags: `--enable-ocr`, `--enable-browser` mark behavior only.
- Artifact schema includes tenant_id, trace_id, pipeline, extracted, quality, pii, fingerprints, policy_fingerprint.
- Troubleshooting: unknown MIME falls back to minimal pipeline; OCR/Browser flags set markers, no processes are spawned.

### Sequence (validated → shadow → artefact → (optional) event)
- Upload/API/Mail erreicht Status „validated“ → Shadow-Flow wird lokal gestartet
- Ergebnis-Artefakt: `artifacts/inbox_local/{ISO8601UTC}_{SHA256}_result.json`
- Log: `mcp_shadow_analysis_done` (PII-frei, nur Artefaktpfad)
- Optionales Outbox-Event (Flag `MCP_SHADOW_EMIT_ANALYSIS_EVENT=true`): `InboxItemAnalysisReady` mit `payload.mcp_artifact_path`

### How-To
- VS Code Task: „Inbox → MCP Shadow Analysis (sample)“
- CLI: `python tools/flows/run_inbox_shadow_for_last_validated.py --tenant 00000000-0000-0000-0000-000000000001`
