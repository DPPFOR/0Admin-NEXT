Inbox Orchestration (Local, Read-Only)

- How to run:
  - CLI: `python tools/flows/run_inbox_local_flow.py --tenant 00000000-0000-0000-0000-000000000001 --path artifacts/inbox/samples/pdf/sample.pdf`
  - Flags: `--enable-ocr`, `--enable-browser` mark behavior only.
- Artifact schema includes tenant_id, trace_id, pipeline, extracted, quality, pii, fingerprints, policy_fingerprint.
- Troubleshooting: unknown MIME falls back to minimal pipeline; OCR/Browser flags set markers, no processes are spawned.

