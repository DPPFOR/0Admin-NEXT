"""Log-only sender DNS checklist generator.

The CLI produces expectation reports for SPF/DKIM/DMARC without touching
real DNS records. Operators must execute the manual commands listed in
the Markdown output to verify the configuration in production.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


ARTIFACT_ROOT = Path("artifacts/reports/mahnwesen")


@dataclass(frozen=True)
class DnsExpectation:
    record_type: str
    name: str
    expected_value: str
    status: str = "UNVERIFIED"


def build_expectations(domain: str) -> list[DnsExpectation]:
    base = f"mail.{domain}"
    selector = "brevo"
    dkim1 = f"{selector}._domainkey.{domain}"
    dkim2 = f"{selector}2._domainkey.{domain}"
    return [
        DnsExpectation(
            record_type="SPF",
            name=domain,
            expected_value="v=spf1 include:spf.brevo.com -all",
        ),
        DnsExpectation(
            record_type="DKIM",
            name=dkim1,
            expected_value=f"CNAME {selector}.domainkey.brevo.com",
        ),
        DnsExpectation(
            record_type="DKIM",
            name=dkim2,
            expected_value=f"CNAME {selector}2.domainkey.brevo.com",
        ),
        DnsExpectation(
            record_type="DMARC",
            name=f"_dmarc.{domain}",
            expected_value="v=DMARC1; p=none; rua=mailto:postmaster@" + domain,
        ),
        DnsExpectation(
            record_type="MX",
            name=base,
            expected_value="<tenant mail relay> (manual verification)",
        ),
    ]


def render_markdown(tenant_id: str, domain: str, expectations: Iterable[DnsExpectation]) -> str:
    lines = [
        f"# Sender DNS Status — Tenant `{tenant_id}`",
        "",
        f"*Generated:* {datetime.now(UTC).isoformat()}",
        f"*Domain:* `{domain}`",
        "",
        "| Record | Name | Expected Value | Status |",
        "| --- | --- | --- | --- |",
    ]
    for exp in expectations:
        lines.append(
            f"| {exp.record_type} | `{exp.name}` | `{exp.expected_value}` | {exp.status} |"
        )

    lines += [
        "",
        "## Manual Verification",
        "",
        "Run the following commands and compare with the expected values:",
        "",
        f"```bash\ndig TXT {domain}\ndig CNAME brevo._domainkey.{domain}\ndig CNAME brevo2._domainkey.{domain}\ndig TXT _dmarc.{domain}\n```",
        "",
        "*Status `UNVERIFIED` indicates that manual validation is pending.*",
    ]

    return "\n".join(lines) + "\n"


def build_report(tenant_id: str, domain: str) -> dict[str, object]:
    expectations = build_expectations(domain)
    return {
        "tenant_id": tenant_id,
        "domain": domain,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "EXPECTED",
        "records": [
            {
                "record_type": exp.record_type,
                "name": exp.name,
                "expected_value": exp.expected_value,
                "status": exp.status,
            }
            for exp in expectations
        ],
        "notes": [
            "Log-only report. Perform manual DNS queries before go-live.",
            "DKIM CNAME values use Brevo placeholders — replace with actual selectors once issued.",
        ],
    }


def write_outputs(tenant_id: str, domain: str, report: dict[str, object]) -> tuple[Path, Path]:
    tenant_dir = ARTIFACT_ROOT / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    json_path = tenant_dir / "sender_dns_status.json"
    md_path = tenant_dir / "sender_dns_status.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    expectations = [
        DnsExpectation(
            record_type=rec["record_type"],
            name=rec["name"],
            expected_value=rec["expected_value"],
            status=rec["status"],
        )
        for rec in report["records"]
    ]
    markdown = render_markdown(tenant_id, domain, expectations)
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate sender DNS expectation report")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    parser.add_argument("--domain", required=True, help="Tenant mail domain")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args.tenant, args.domain)
    json_path, md_path = write_outputs(args.tenant, args.domain, report)
    print(json.dumps({
        "tenant_id": args.tenant,
        "domain": args.domain,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "status": report["status"],
    }, ensure_ascii=False))
    print("DNS expectations written (manual verification required).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

