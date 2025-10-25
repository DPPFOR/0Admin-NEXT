# Inbox Quality Definition of Done

This document summarises the Definition of Done (DoD) logic for parsed inbox items. Each document type applies a specific scoring model to derive `confidence`, `quality_status`, and an optional list of validation rules. All scores are expressed as percentages (0–100). Unless noted otherwise, rules with `level="error"` block acceptance but the importer remains idempotent and durable: rejected items are still persisted (unless the importer is run with `--strict`).

## Invoice (baseline)

- Required fields: `amount`, `invoice_no`, `due_date`, and at least one structured table.
- Confidence uses the existing invoice heuristics (required fields, table quality, plausibility, source quality).
- Quality status:
  - `accepted`: required fields present and confidence ≥ 70.
  - `needs_review`: partial data or reduced confidence.
  - `rejected`: no required fields or confidence < 50.

## Payment

- Inputs: amount (`Decimal > 0`), currency (`EUR|USD|GBP`), payment date (`YYYY-MM-DD`), counterparty (non-empty string).
- Scoring:
  - Base score: 70.
  - +10 if currency is in the supported list.
  - +10 if payment date is present and valid.
  - +10 if counterparty is present.
- Quality status:
  - `accepted`: score ≥ 80 and no blocking rules.
  - `needs_review`: score ≥ 60 but < 80, or soft warnings raised.
  - `rejected`: missing amount, score < 60, or any hard failure.
- Notes:
  - Currency is normalised to upper-case (e.g. `eur` → `EUR`).
  - All validation findings are surfaced via `rules` with codes like `payment.amount.invalid`.

## Other

- Triggered when invoice heuristics fail but the document still contains usable structure (key/value pairs or table rows).
- Scoring:
  - Base score: 40.
  - +10 if at least one non-empty key/value entry is present.
  - +10 if a table with at least one populated cell is present.
  - +10 synergy bonus when both structures exist.
  - +10 if the combined structured values yield at least three non-empty cells.
  - Raw score is capped at 90; reported confidence is capped at 60.
- Quality status:
  - `accepted`: raw score ≥ 65.
  - `needs_review`: raw score 50–64.
  - `rejected`: no structure or raw score < 50.
- All structural gaps are emitted as warnings (e.g. `other.structure.empty`) to help triage manually.

## Importer Behaviour

- The importer chooses `doctype` based on pipeline hints:
  - Explicit `doc_type` or pipeline steps containing `payment`, `iban`, `bic`, etc. force a payment classification.
  - When invoice validation fails and meaningful structure exists, the importer falls back to `doctype="other"`.
- Flags:
  - `--no-enforce-invoice` disables automatic invoice promotion when required fields are missing.
  - `--no-enforce-payment` or `--no-enforce-other` allow temporary opt-outs while testing.
  - `--strict` will raise if the resulting `quality_status` is `rejected`; otherwise rejected items are still upserted.
- Chunks:
  - Table data is stored with `kind="table"`, and key/value entries are aggregated into a `kind="kv"` chunk to keep downstream processing deterministic.

## OCR & Table-Boost (flags only)

- The Inbox local flow exposes the marker flags `enable_ocr`, `enable_table_boost`, and `mvr_preview` via CLI switches.
- These flags do **not** invoke OCR/Table-Boost at runtime; they are persisted as metadata (`parsed_items.flags`) so downstream services can preview planned work.
- When `mvr_preview` is set, the importer records `mvr_preview=true` and a placeholder `mvr_score=0.00` on the parsed item and surfaces the same via the read-model.
- Future enablement can pivot on the stored flags without changing database schema again; simply toggle the actual adapters when the runtime feature is ready.

## Rule Codes

Common rule codes emitted by the new doctypes:

| Code                            | Description                                  | Level   |
|--------------------------------|----------------------------------------------|---------|
| `payment.amount.invalid`       | Amount missing or ≤ 0                         | error   |
| `payment.currency.unsupported` | Currency not in the EUR/USD/GBP allowlist     | error   |
| `payment.date.missing`         | Payment date missing or invalid               | error   |
| `payment.counterparty.missing` | Counterparty missing                          | error   |
| `other.fields.missing`         | No key/value entries found                    | warning |
| `other.tables.missing`         | No structured tables detected                 | warning |
| `other.structure.empty`        | No structured content captured                | error   |

Downstream systems should treat the combination of `quality_status` and `rules` as the canonical readiness indicator.
