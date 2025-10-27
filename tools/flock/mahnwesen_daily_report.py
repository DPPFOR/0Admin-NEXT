#!/usr/bin/env python3
"""Mahnwesen Daily Report Generator.

Generates daily CSV/JSON reports with aggregates per stage,
sum of amounts, and customer counts.
"""

import argparse
import csv
import json

# Add project root to path
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.mahnwesen import DunningConfig
from agents.mahnwesen.clients import ReadApiClient


def generate_daily_report(
    tenant_id: str,
    output_path: str | None = None,
    base_url: str = "http://localhost:8000",
    date_override: str | None = None,
) -> dict:
    """Generate daily report for tenant.

    Args:
        tenant_id: Tenant ID
        output_path: Output file path
        base_url: API base URL
        date_override: Override date (YYYY-MM-DD)

    Returns:
        Report data dictionary
    """
    if date_override:
        try:
            report_date = datetime.fromisoformat(date_override).date()
        except ValueError:
            report_date = datetime.now(UTC).date()
    else:
        report_date = datetime.now(UTC).date()

    # Generate report data
    report_data = {
        "tenant_id": tenant_id,
        "report_date": report_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "unknown",
        "summary": {
            "total_overdue": 0,
            "stage_1_count": 0,
            "stage_2_count": 0,
            "stage_3_count": 0,
            "total_amount_cents": 0,
            "unique_customers": 0,
            "avg_amount": 0.0,
        },
        "stages": {
            "stage_1": {"count": 0, "amount_cents": 0, "customers": set()},
            "stage_2": {"count": 0, "amount_cents": 0, "customers": set()},
            "stage_3": {"count": 0, "amount_cents": 0, "customers": set()},
        },
        "errors": [],
        "warnings": [],
    }

    try:
        # Create config and client
        config = DunningConfig(tenant_id=tenant_id, read_api_base_url=base_url)
        client = ReadApiClient(config)
        response = client.get_overdue_invoices()
        invoices = response.invoices

        # Process invoices
        for invoice in invoices:
            amount_cents = invoice.amount_cents
            days_overdue = invoice.days_overdue
            customer_id = invoice.customer_id or invoice.customer_name or "unknown"

            # Determine stage
            if days_overdue >= 30:
                stage = "stage_3"
            elif days_overdue >= 14:
                stage = "stage_2"
            elif days_overdue >= 3:
                stage = "stage_1"
            else:
                continue  # Skip if not overdue enough

            # Update stage data
            report_data["stages"][stage]["count"] += 1
            report_data["stages"][stage]["amount_cents"] += amount_cents
            report_data["stages"][stage]["customers"].add(customer_id)

            # Update summary
            report_data["summary"]["total_overdue"] += 1
            report_data["summary"]["total_amount_cents"] += amount_cents

            if stage == "stage_1":
                report_data["summary"]["stage_1_count"] += 1
            elif stage == "stage_2":
                report_data["summary"]["stage_2_count"] += 1
            elif stage == "stage_3":
                report_data["summary"]["stage_3_count"] += 1

        # Calculate unique customers
        all_customers = set()
        for stage_data in report_data["stages"].values():
            all_customers.update(stage_data["customers"])

        report_data["summary"]["unique_customers"] = len(all_customers)

        # Calculate average amount
        if report_data["summary"]["total_overdue"] > 0:
            report_data["summary"]["avg_amount"] = report_data["summary"]["total_amount_cents"] / (
                report_data["summary"]["total_overdue"] * 100
            )

        # Convert sets to lists for JSON serialization
        for stage_data in report_data["stages"].values():
            stage_data["customers"] = list(stage_data["customers"])

        report_data["status"] = "success"

    except Exception as e:
        report_data["status"] = "error"
        report_data["errors"].append(f"Failed to fetch data: {str(e)}")

        # Convert sets to lists for JSON serialization even in error case
        for stage_data in report_data["stages"].values():
            stage_data["customers"] = list(stage_data["customers"])

    # Save report
    if output_path:
        save_report(report_data, output_path)
    else:
        # Default path
        report_dir = Path("artifacts/reports/mahnwesen") / tenant_id
        report_dir.mkdir(parents=True, exist_ok=True)

        # Save as JSON
        json_path = report_dir / f"daily_{report_date.strftime('%Y%m%d')}.json"
        save_report(report_data, str(json_path))

        # Save as CSV
        csv_path = report_dir / f"daily_{report_date.strftime('%Y%m%d')}.csv"
        save_csv_report(report_data, str(csv_path))

    return report_data


def save_report(report_data: dict, output_path: str) -> None:
    """Save report as JSON.

    Args:
        report_data: Report data
        output_path: Output file path
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)


def save_csv_report(report_data: dict, output_path: str) -> None:
    """Save report as CSV.

    Args:
        report_data: Report data
        output_path: Output file path
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow(
            [
                "tenant_id",
                "report_date",
                "status",
                "total_overdue",
                "stage_1_count",
                "stage_2_count",
                "stage_3_count",
                "total_amount_cents",
                "unique_customers",
                "avg_amount",
            ]
        )

        # Data row
        summary = report_data["summary"]
        writer.writerow(
            [
                report_data["tenant_id"],
                report_data["report_date"],
                report_data["status"],
                summary["total_overdue"],
                summary["stage_1_count"],
                summary["stage_2_count"],
                summary["stage_3_count"],
                summary["total_amount_cents"],
                summary["unique_customers"],
                f"{summary['avg_amount']:.2f}",
            ]
        )


def print_summary(report_data: dict) -> None:
    """Print report summary to console.

    Args:
        report_data: Report data
    """
    print("\n" + "=" * 60)
    print("MAHNWESEN DAILY REPORT")
    print("=" * 60)
    print(f"Tenant: {report_data['tenant_id']}")
    print(f"Date: {report_data['report_date']}")
    print(f"Status: {report_data['status'].upper()}")
    print("-" * 60)

    summary = report_data["summary"]
    print(f"Total Overdue: {summary['total_overdue']}")
    print(f"Stage 1: {summary['stage_1_count']}")
    print(f"Stage 2: {summary['stage_2_count']}")
    print(f"Stage 3: {summary['stage_3_count']}")
    print(f"Total Amount: {summary['total_amount_cents'] / 100:.2f} EUR")
    print(f"Unique Customers: {summary['unique_customers']}")
    print(f"Average Amount: {summary['avg_amount']:.2f} EUR")

    if report_data.get("warnings"):
        print(f"\nWarnings: {len(report_data['warnings'])}")
        for warning in report_data["warnings"]:
            print(f"  - {warning}")

    if report_data.get("errors"):
        print(f"\nErrors: {len(report_data['errors'])}")
        for error in report_data["errors"]:
            print(f"  - {error}")

    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Mahnwesen Daily Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate daily report for tenant
  python tools/flock/mahnwesen_daily_report.py --tenant 00000000-0000-0000-0000-000000000001
  
  # Generate report for specific date
  python tools/flock/mahnwesen_daily_report.py --tenant 00000000-0000-0000-0000-000000000001 --date 2025-02-15
  
  # Save to custom path
  python tools/flock/mahnwesen_daily_report.py --tenant 00000000-0000-0000-0000-000000000001 --out /tmp/report.json
        """,
    )

    parser.add_argument("--tenant", required=True, help="Tenant ID (UUID format)")

    parser.add_argument(
        "--out",
        help="Output file path (default: artifacts/reports/mahnwesen/<tenant>/daily_YYYYMMDD.{json,csv})",
    )

    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Read-API base URL (default: http://localhost:8000)",
    )

    parser.add_argument("--date", help="Override date (YYYY-MM-DD format)")

    parser.add_argument("--quiet", action="store_true", help="Suppress console output")

    args = parser.parse_args()

    try:
        report_data = generate_daily_report(
            tenant_id=args.tenant,
            output_path=args.out,
            base_url=args.base_url,
            date_override=args.date,
        )

        if not args.quiet:
            print_summary(report_data)

            if not args.out:
                print("\nReport saved to:")
                print(
                    f"  JSON: artifacts/reports/mahnwesen/{args.tenant}/daily_{report_data['report_date'].replace('-', '')}.json"
                )
                print(
                    f"  CSV:  artifacts/reports/mahnwesen/{args.tenant}/daily_{report_data['report_date'].replace('-', '')}.csv"
                )

        # Exit with error if report failed
        if report_data["status"] == "error":
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nReport generation interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
