"""E-Invoice Batch-Generator für Factur-X und XRechnung Stubs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Callable, Iterable, List

from agents.einvoice import (
    FacturXValidationResult,
    NumberingService,
    XRechnungValidationResult,
    approve,
    build_facturx_document,
    build_sample_invoice,
    build_sample_profile,
    build_xrechnung_document,
    facturx_version,
    iter_sample_scenarios,
    validate_facturx,
    validate_xrechnung,
    write_package,
    xrechnung_version,
)
from agents.einvoice.summary import RunSummary, collect_results, write_summary_markdown


def _iso_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _make_now_provider(start: datetime) -> Callable[[], datetime]:
    tick = count()

    def _next() -> datetime:
        return start + timedelta(seconds=next(tick))

    return _next


def _ensure_count(count_value: int, scenarios: Iterable) -> List:
    scenarios_list = list(scenarios)
    if count_value > len(scenarios_list):
        raise ValueError(
            f"Requested {count_value} invoices but only {len(scenarios_list)} scenarios available"
        )
    return scenarios_list[:count_value]


def generate_batch(
    *,
    tenant_id: str,
    count: int,
    base_dir: Path,
    now_provider_factory: Callable[[], Callable[[], datetime]],
    dry_run: bool = False,
    verbose: bool = False,
    format_name: str = "facturx",
) -> dict:
    scenarios = _ensure_count(count, iter_sample_scenarios())
    profile = build_sample_profile(tenant_id)
    results: List[dict] = []
    previous_hash: str | None = None
    first_document_timestamp: datetime | None = None

    now_provider = now_provider_factory()
    numbering = NumberingService(clock=now_provider)

    for scenario in scenarios:
        invoice_id = f"{tenant_id}-{scenario.code}"
        issue_date = datetime(2025, 1, 1, tzinfo=timezone.utc).date()
        due_date = datetime(2025, 1, 15, tzinfo=timezone.utc).date()
        invoice = build_sample_invoice(
            scenario,
            invoice_id=invoice_id,
            tenant_id=tenant_id,
            issue_date=issue_date,
            due_date=due_date,
            payment_terms=profile.payment_terms,
            now_provider=now_provider,
        )

        reservation_id = numbering.reserve(tenant_id, invoice.issue_date)
        invoice_no = numbering.commit(reservation_id)
        invoice.invoice_no = invoice_no

        document_timestamp = now_provider()

        if first_document_timestamp is None:
            first_document_timestamp = document_timestamp

        if format_name == "facturx":
            pdf_bytes, xml_bytes = build_facturx_document(
                invoice,
                profile,
                document_timestamp,
            )
            validation_result: FacturXValidationResult = validate_facturx(xml_bytes)
            files = {
                "invoice.pdf": pdf_bytes,
                "invoice.xml": xml_bytes,
                "validation.json": json.dumps(
                    validation_result.to_dict(), indent=2, sort_keys=True
                ).encode("utf-8"),
            }
            archive_invoice_no = invoice_no
            generator_version = facturx_version()
            format_identifier = "facturx"
        elif format_name == "xrechnung":
            xml_bytes = build_xrechnung_document(
                invoice,
                profile,
                document_timestamp,
            )
            validation_result = validate_xrechnung(xml_bytes)
            files = {
                "invoice.xml": xml_bytes,
                "validation.json": json.dumps(
                    validation_result.to_dict(), indent=2, sort_keys=True
                ).encode("utf-8"),
            }
            archive_invoice_no = f"{invoice_no}-xrechnung"
            generator_version = xrechnung_version()
            format_identifier = "xrechnung-ubl"
        else:
            raise ValueError(f"Unsupported format: {format_name}")

        idempotency_key = invoice.idempotency_key(invoice_no, format_identifier)

        result_entry = {
            "invoice_no": invoice_no,
            "invoice_id": invoice_id,
            "format": format_name,
            "idempotency_key": idempotency_key,
            "validation": validation_result.to_dict(),
        }

        if dry_run:
            result_entry.update(
                {
                    "manifest_hash": previous_hash,
                    "dry_run": True,
                }
            )
            results.append(result_entry)
            continue

        package_timestamp = now_provider()
        package_dir, manifest_hash = write_package(
            base_dir,
            tenant_id,
            archive_invoice_no,
            files,
            now=package_timestamp,
            previous_hash=previous_hash,
            generator_version=generator_version,
        )
        approve_timestamp = now_provider()
        approve(package_dir, archive_invoice_no, now=approve_timestamp)
        result_entry.update(
            {
                "manifest_hash": manifest_hash,
                "path": str(package_dir),
            }
        )
        results.append(result_entry)
        previous_hash = manifest_hash
        if verbose:
            print(f"Generated {invoice_no} -> {manifest_hash}")

    summary_path = None
    if not dry_run and results:
        summary = RunSummary(
            tenant_id=tenant_id,
            format=format_name,
            generator_version=generator_version,
            created_at=first_document_timestamp or datetime.now(timezone.utc),
            results=collect_results(results),
        )
        summary_path = write_summary_markdown(summary, base_dir)
        if verbose:
            print(f"Summary written to {summary_path}")

    return {
        "invoices": results,
        "summary_path": str(summary_path) if summary_path else None,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate e-invoice batches")
    parser.add_argument("--tenant", required=True, help="Tenant-ID")
    parser.add_argument("--count", type=int, default=10, help="Anzahl Rechnungen")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Basisverzeichnis für Artefakte",
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur Simulation, keine Writes")
    parser.add_argument("--verbose", action="store_true", help="Zusätzliche Logs")
    parser.add_argument(
        "--now",
        help="ISO-8601 Zeitstempel für deterministische Läufe (z. B. 2025-01-01T00:00:00+00:00)",
    )
    parser.add_argument(
        "--format",
        choices=["facturx", "xrechnung"],
        default="facturx",
        help="Ausgabeformat (default: facturx)",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    if args.count <= 0:
        raise SystemExit("Count must be positive")
    base_now = _iso_datetime(args.now) if args.now else datetime.now(timezone.utc)

    def factory() -> Callable[[], datetime]:
        return _make_now_provider(base_now)

    output = generate_batch(
        tenant_id=args.tenant,
        count=args.count,
        base_dir=args.output_dir,
        now_provider_factory=factory,
        dry_run=args.dry_run,
        verbose=args.verbose,
        format_name=args.format,
    )
    if args.verbose:
        print(json.dumps(output, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()

