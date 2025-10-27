#!/usr/bin/env python3
"""Mahnwesen Console Dashboard.

Simple console-based dashboard for monitoring dunning status.
Shows today's processed cases, open overdue by stage, and planned notices.
"""

import argparse
import json

# Add project root to path
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.mahnwesen.clients import ReadApiClient


def load_dry_run_report(tenant_id: str, date_override: str | None = None) -> dict | None:
    """Load dry-run report for tenant.

    Args:
        tenant_id: Tenant ID
        date_override: Override date (YYYY-MM-DD)

    Returns:
        Report data or None if not found
    """
    if date_override:
        try:
            report_date = datetime.fromisoformat(date_override).date()
        except ValueError:
            report_date = datetime.now(UTC).date()
    else:
        report_date = datetime.now(UTC).date()

    report_path = (
        Path("artifacts/reports/mahnwesen")
        / tenant_id
        / f"dry_run_{report_date.strftime('%Y%m%d')}.json"
    )

    if not report_path.exists():
        return None

    try:
        with open(report_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def fetch_overdue_invoices(tenant_id: str, base_url: str = "http://localhost:8000") -> list[dict]:
    """Fetch overdue invoices from Read-API.

    Args:
        tenant_id: Tenant ID
        base_url: API base URL

    Returns:
        List of overdue invoices
    """
    try:
        client = ReadApiClient(base_url=base_url)
        response = client.fetch_overdue_invoices(tenant_id)
        return response.get("items", [])
    except Exception:
        return []


def print_dashboard(
    tenant_id: str, base_url: str = "http://localhost:8000", date_override: str | None = None
):
    """Print dashboard for tenant.

    Args:
        tenant_id: Tenant ID
        base_url: API base URL
        date_override: Override date (YYYY-MM-DD)
    """
    print("=" * 80)
    print("MAHNWESEN DASHBOARD")
    print("=" * 80)
    print(f"Tenant: {tenant_id}")
    print(f"Date: {date_override or datetime.now(UTC).strftime('%Y-%m-%d')}")
    print(f"Time: {datetime.now(UTC).strftime('%H:%M:%S')} UTC")
    print("-" * 80)

    # Load dry-run report
    report = load_dry_run_report(tenant_id, date_override)

    if report:
        print("📊 TODAY'S DRY-RUN SUMMARY")
        print("-" * 40)
        summary = report.get("summary", {})
        print(f"Total Overdue: {summary.get('total_overdue', 0)}")
        print(f"Stage 1: {summary.get('stage_1_count', 0)}")
        print(f"Stage 2: {summary.get('stage_2_count', 0)}")
        print(f"Stage 3: {summary.get('stage_3_count', 0)}")
        print(f"Notices Created: {summary.get('notices_created', 0)}")
        print(f"Events Dispatched: {summary.get('events_dispatched', 0)}")
        print(f"Processing Time: {summary.get('processing_time_seconds', 0.0):.2f}s")

        if report.get("warnings"):
            print(f"\n⚠️  Warnings: {len(report['warnings'])}")
            for warning in report["warnings"][:3]:  # Show first 3
                print(f"  - {warning}")

        if report.get("errors"):
            print(f"\n❌ Errors: {len(report['errors'])}")
            for error in report["errors"][:3]:  # Show first 3
                print(f"  - {error}")
    else:
        print("📊 TODAY'S DRY-RUN SUMMARY")
        print("-" * 40)
        print("No dry-run report found for today")
        print("Run: python tools/flock/playbook_mahnwesen.py --tenant <id> --dry-run")

    print("\n" + "-" * 80)

    # Fetch current overdue invoices
    print("🔍 CURRENT OVERDUE INVOICES")
    print("-" * 40)

    try:
        overdue_invoices = fetch_overdue_invoices(tenant_id, base_url)

        if overdue_invoices:
            # Group by stage (simplified)
            stage_1 = [
                inv
                for inv in overdue_invoices
                if inv.get("days_overdue", 0) >= 3 and inv.get("days_overdue", 0) < 14
            ]
            stage_2 = [
                inv
                for inv in overdue_invoices
                if inv.get("days_overdue", 0) >= 14 and inv.get("days_overdue", 0) < 30
            ]
            stage_3 = [inv for inv in overdue_invoices if inv.get("days_overdue", 0) >= 30]

            print(f"Stage 1 (3-13 days): {len(stage_1)}")
            print(f"Stage 2 (14-29 days): {len(stage_2)}")
            print(f"Stage 3 (30+ days): {len(stage_3)}")

            # Show recent invoices
            recent = sorted(overdue_invoices, key=lambda x: x.get("due_date", ""), reverse=True)[:5]
            print(f"\nRecent Overdue ({len(recent)} of {len(overdue_invoices)}):")
            for inv in recent:
                invoice_no = inv.get("invoice_number", inv.get("invoice_id", "N/A"))
                amount = inv.get("amount", 0)
                days = inv.get("days_overdue", 0)
                print(f"  - {invoice_no}: {amount:.2f} EUR ({days} days)")
        else:
            print("No overdue invoices found")
            print("✅ All invoices are up to date!")
    except Exception as e:
        print(f"❌ Error fetching overdue invoices: {e}")
        print("💡 Check if Read-API is running on", base_url)

    print("\n" + "=" * 80)
    print("QUICK ACTIONS:")
    print("• Dry-run: python tools/flock/playbook_mahnwesen.py --tenant <id> --dry-run")
    print("• Daily report: python tools/flock/mahnwesen_daily_report.py --tenant <id>")
    print("• VS Code Task: Ctrl+Shift+P → 'Tasks: Run Task' → 'Mahnwesen: Dry-Run (Go-Live)'")
    print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Mahnwesen Console Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show dashboard for tenant
  python tools/flock/mahnwesen_console.py --tenant 00000000-0000-0000-0000-000000000001
  
  # Show dashboard for specific date
  python tools/flock/mahnwesen_console.py --tenant 00000000-0000-0000-0000-000000000001 --date 2025-02-15
  
  # Use different API URL
  python tools/flock/mahnwesen_console.py --tenant 00000000-0000-0000-0000-000000000001 --base-url http://localhost:8000
        """,
    )

    parser.add_argument("--tenant", required=True, help="Tenant ID (UUID format)")

    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Read-API base URL (default: http://localhost:8000)",
    )

    parser.add_argument("--date", help="Override date (YYYY-MM-DD format)")

    args = parser.parse_args()

    try:
        print_dashboard(args.tenant, args.base_url, args.date)
    except KeyboardInterrupt:
        print("\n\nDashboard interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
