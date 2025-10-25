"""KPI Reporting System for Mahnwesen.

This module generates daily KPI reports with cycle time metrics.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json

from zoneinfo import ZoneInfo


@dataclass
class CycleTimeEntry:
    """Represents a single cycle time measurement."""
    invoice_id: str
    stage: int
    created_at: datetime
    sent_at: Optional[datetime] = None
    cycle_time_hours: Optional[float] = None


@dataclass
class DailyKPIReport:
    """Daily KPI report for a tenant."""
    tenant_id: str
    report_date: str  # YYYY-MM-DD
    timezone: str
    total_overdue: int = 0
    notices_created: int = 0
    notices_sent: int = 0
    cycle_time_median: Optional[float] = None
    cycle_times: List[float] = None
    stage_1_count: int = 0
    stage_2_count: int = 0
    stage_3_count: int = 0
    error_rate: float = 0.0

    def __post_init__(self):
        if self.cycle_times is None:
            self.cycle_times = []


class MahnwesenKPI:
    """KPI engine for Mahnwesen reporting."""

    def __init__(self):
        """Initialize KPI engine."""
        self.logger = logging.getLogger(__name__)
        self.timezone = ZoneInfo("Europe/Berlin")

    def generate_daily_report(
        self,
        tenant_id: str,
        target_date: Optional[datetime] = None
    ) -> DailyKPIReport:
        """Generate daily KPI report for a tenant.

        Args:
            tenant_id: Tenant identifier
            target_date: Target date (defaults to today)

        Returns:
            Daily KPI report
        """
        if target_date is None:
            target_date = datetime.now(self.timezone)

        # Convert to Berlin timezone if not already
        if target_date.tzinfo != self.timezone:
            target_date = target_date.astimezone(self.timezone)

        # Get date string in YYYY-MM-DD format
        report_date_str = target_date.strftime("%Y-%m-%d")

        # Create base report
        report = DailyKPIReport(
            tenant_id=tenant_id,
            report_date=report_date_str,
            timezone="Europe/Berlin"
        )

        # TODO: In production, fetch real data from database/log files
        # For now, simulate some sample data
        report = self._simulate_sample_data(report)

        # Calculate median cycle time if we have data
        if report.cycle_times:
            sorted_times = sorted(report.cycle_times)
            n = len(sorted_times)
            if n % 2 == 1:
                report.cycle_time_median = sorted_times[n // 2]
            else:
                mid1 = sorted_times[n // 2 - 1]
                mid2 = sorted_times[n // 2]
                report.cycle_time_median = (mid1 + mid2) / 2

        return report

    def _simulate_sample_data(self, report: DailyKPIReport) -> DailyKPIReport:
        """Simulate sample KPI data for testing.

        Args:
            report: Base report to enhance

        Returns:
            Enhanced report with sample data
        """
        # Simulate realistic KPI data
        import random
        random.seed(hash(report.tenant_id + report.report_date))  # Deterministic seeding

        report.total_overdue = random.randint(50, 200)
        report.notices_created = random.randint(10, 50)
        report.notices_sent = report.notices_created - random.randint(0, 3)  # Some failures
        report.stage_1_count = report.notices_created * 0.7  # 70% stage 1
        report.stage_2_count = report.notices_created * 0.25  # 25% stage 2
        report.stage_3_count = report.notices_created * 0.05  # 5% stage 3
        report.error_rate = (report.notices_created - report.notices_sent) / max(1, report.notices_created)

        # Generate sample cycle times (in hours)
        cycle_times = []
        for _ in range(report.notices_sent):
            # Most within 24-72 hours, some outliers
            if random.random() < 0.8:
                cycle_time = random.uniform(24, 72)
            else:
                cycle_time = random.uniform(72, 168)  # Up to 7 days
            cycle_times.append(round(cycle_time, 2))

        report.cycle_times = cycle_times

        return report

    def save_report(self, report: DailyKPIReport, output_path: Optional[Path] = None) -> Path:
        """Save KPI report to files.

        Args:
            report: KPI report to save
            output_path: Custom output path (optional)

        Returns:
            Path where report was saved
        """
        if output_path is None:
            base_path = Path("artifacts/reports/mahnwesen")
            output_path = base_path / report.tenant_id / f"{report.report_date}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save JSON version
        json_data = {
            "tenant_id": report.tenant_id,
            "report_date": report.report_date,
            "timezone": report.timezone,
            "total_overdue": report.total_overdue,
            "notices_created": report.notices_created,
            "notices_sent": report.notices_sent,
            "cycle_time_median": report.cycle_time_median,
            "stage_1_count": int(round(report.stage_1_count)),
            "stage_2_count": int(round(report.stage_2_count)),
            "stage_3_count": int(round(report.stage_3_count)),
            "error_rate": report.error_rate,
            "generated_at": datetime.now(self.timezone).isoformat(),
            "version": "1.0"
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        # Save Markdown version
        md_path = output_path.with_suffix('.md')
        md_content = f"""# Mahnwesen KPIs - {report.tenant_id}
**Datum:** {report.report_date}  
**Zeitzone:** {report.timezone}

## Übersicht
- **Überfällige Rechnungen:** {report.total_overdue}
- **Erstellte Mahnungen:** {report.notices_created}
- **Versandte Mahnungen:** {report.notices_sent}
- **Fehlerrate:** {report.error_rate:.1%}

## Durchlaufzeiten (Cycle Times)
- **Median:** {report.cycle_time_median or 'N/A'} Stunden
- **Min:** {min(report.cycle_times) if report.cycle_times else 'N/A'} Stunden
- **Max:** {max(report.cycle_times) if report.cycle_times else 'N/A'} Stunden
- **Durchschnitt:** {sum(report.cycle_times)/len(report.cycle_times) if report.cycle_times else 'N/A':.1f} Stunden

## Stufen-Verteilung
- **Stufe 1:** {int(report.stage_1_count)}
- **Stufe 2:** {int(report.stage_2_count)}
- **Stufe 3:** {int(report.stage_3_count)}

---
*Generiert am: {datetime.now(self.timezone).strftime('%Y-%m-%d %H:%M:%S %Z')}*
"""

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        self.logger.info(f"KPI report saved: {output_path}")
        return output_path

    def generate_batch_reports(self, tenant_ids: List[str], target_date: Optional[datetime] = None) -> List[Path]:
        """Generate KPI reports for multiple tenants.

        Args:
            tenant_ids: List of tenant IDs
            target_date: Target date for reports

        Returns:
            List of saved report paths
        """
        saved_paths = []

        for tenant_id in tenant_ids:
            try:
                report = self.generate_daily_report(tenant_id, target_date)
                path = self.save_report(report)
                saved_paths.append(path)
            except Exception as e:
                self.logger.error(f"Failed to generate KPI report for tenant {tenant_id}: {e}")

        return saved_paths


def generate_daily_kpis():
    """Command-line function to generate daily KPIs."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m agents.mahnwesen.kpi <tenant_id> [date]")
        sys.exit(1)

    tenant_id = sys.argv[1]
    target_date = None

    if len(sys.argv) > 2:
        try:
            target_date = datetime.fromisoformat(sys.argv[2])
        except ValueError:
            print(f"Invalid date format: {sys.argv[2]}. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
            sys.exit(1)

    kpi = MahnwesenKPI()
    report = kpi.generate_daily_report(tenant_id, target_date)
    path = kpi.save_report(report)

    print(f"KPI report generated: {path}")
    print(f"Cycle time median: {report.cycle_time_median or 'N/A'} hours")


if __name__ == "__main__":
    generate_daily_kpis()
