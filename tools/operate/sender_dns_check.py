"""Sender DNS checklist generator with auto-verification.

The CLI produces expectation reports for SPF/DKIM/DMARC and optionally
verifies records against real DNS lookups using dig.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, replace
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
    actual_value: str | None = None


def build_expectations_brevo(domain: str) -> list[DnsExpectation]:
    """Build DNS expectations for Brevo provider."""
    dkim1 = f"brevo1._domainkey.{domain}"
    dkim2 = f"brevo2._domainkey.{domain}"
    return [
        DnsExpectation(
            record_type="SPF",
            name=domain,
            expected_value="v=spf1 include:spf.brevo.com ~all or -all",
        ),
        DnsExpectation(
            record_type="DKIM",
            name=dkim1,
            expected_value="CNAME b1.dppfor-eu.dkim.brevo.com.",
        ),
        DnsExpectation(
            record_type="DKIM",
            name=dkim2,
            expected_value="CNAME b2.dppfor-eu.dkim.brevo.com.",
        ),
        DnsExpectation(
            record_type="DMARC",
            name=f"_dmarc.{domain}",
            expected_value="v=DMARC1; p=...",
        ),
    ]


def build_expectations(domain: str, provider: str | None = None) -> list[DnsExpectation]:
    """Build DNS expectations for given domain and provider."""
    if provider == "brevo":
        return build_expectations_brevo(domain)
    
    # Legacy default (deprecated)
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


def lookup_dns(record_type: str, name: str, verbose: bool = False) -> str | None:
    """Lookup DNS record using dig. Returns None on failure.
    
    For TXT records, returns the first matching record (SPF or DMARC).
    For CNAME records, returns the target value.
    """
    try:
        if record_type == "SPF":
            query_type = "TXT"
        elif record_type == "DMARC":
            query_type = "TXT"
        elif record_type == "DKIM":
            query_type = "CNAME"
        else:
            return None
        
        result = subprocess.run(
            ["dig", "+short", query_type, name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            if verbose:
                print(f"  dig failed for {name} ({query_type}): {result.stderr}", file=__import__("sys").stderr)
            return None
        
        # dig +short returns one or more lines
        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        if not lines:
            return None
        
        if query_type == "TXT":
            # TXT records: remove quotes and join (dig may split long TXT records)
            # Find the record matching our type
            for line in lines:
                value = line.strip('"').strip()
                if record_type == "SPF" and value.startswith("v=spf1"):
                    if verbose:
                        print(f"  dig {query_type} {name}: {value}")
                    return value
                elif record_type == "DMARC" and value.startswith("v=DMARC1"):
                    if verbose:
                        print(f"  dig {query_type} {name}: {value}")
                    return value
            # If no match found, return first line as fallback
            value = lines[0].strip('"').strip()
            if verbose:
                print(f"  dig {query_type} {name}: {value} (fallback)")
            return value
        else:
            # CNAME: return first line, remove trailing dot and quotes
            value = lines[0].strip('"').rstrip(".")
            if verbose:
                print(f"  dig {query_type} {name}: {value}")
            return value
    except Exception as e:
        if verbose:
            print(f"  Exception during DNS lookup for {name}: {e}", file=__import__("sys").stderr)
        return None


def verify_spf_brevo(actual: str | None) -> bool:
    """Verify SPF record matches Brevo pattern: include:spf.brevo.com ~all or -all."""
    if not actual:
        return False
    # Strip whitespace to handle trailing spaces from DNS queries
    actual = actual.strip()
    pattern = r"^v=spf1\s+include:spf\.brevo\.com\s+(~all|-all)$"
    return bool(re.match(pattern, actual, re.IGNORECASE))


def verify_dkim_brevo(actual: str | None, expected_target: str) -> bool:
    """Verify DKIM CNAME matches expected target (trailing dot optional)."""
    if not actual:
        return False
    # Remove trailing dot for comparison
    actual_clean = actual.rstrip(".")
    expected_clean = expected_target.rstrip(".")
    # CNAME value might be prefixed with "CNAME " or just the target
    if actual_clean.startswith("CNAME "):
        actual_clean = actual_clean[6:].strip()
    return actual_clean.lower() == expected_clean.lower()


def verify_dmarc_brevo(actual: str | None) -> bool:
    """Verify DMARC record starts with v=DMARC1; and contains p=."""
    if not actual:
        return False
    # Remove quotes if present
    actual_clean = actual.strip('"')
    return (
        actual_clean.startswith("v=DMARC1;")
        and "p=" in actual_clean
    )


def verify_expectation(exp: DnsExpectation, provider: str | None, verbose: bool = False) -> DnsExpectation:
    """Verify a single DNS expectation against real DNS."""
    if provider != "brevo":
        return exp  # No verification for other providers
    
    actual = lookup_dns(exp.record_type, exp.name, verbose)
    verified = False
    
    if exp.record_type == "SPF":
        verified = verify_spf_brevo(actual)
    elif exp.record_type == "DKIM":
        # Extract target from expected_value (format: "CNAME b1.dppfor-eu.dkim.brevo.com.")
        target = exp.expected_value.replace("CNAME ", "").strip()
        verified = verify_dkim_brevo(actual, target)
    elif exp.record_type == "DMARC":
        verified = verify_dmarc_brevo(actual)
    else:
        # MX and others: skip verification
        verified = False
    
    status = "VERIFIED" if verified else "UNVERIFIED"
    return replace(exp, status=status, actual_value=actual)


def render_markdown(tenant_id: str, domain: str, expectations: Iterable[DnsExpectation]) -> str:
    lines = [
        f"# Sender DNS Status — Tenant `{tenant_id}`",
        "",
        f"*Generated:* {datetime.now(UTC).isoformat()}",
        f"*Domain:* `{domain}`",
        "",
        "| Record | Name | Expected Value | Actual Value | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for exp in expectations:
        actual_display = f"`{exp.actual_value}`" if exp.actual_value else "*not checked*"
        lines.append(
            f"| {exp.record_type} | `{exp.name}` | `{exp.expected_value}` | {actual_display} | {exp.status} |"
        )

    # Generate dig commands dynamically based on expectations
    dig_commands = []
    for exp in expectations:
        if exp.record_type == "SPF":
            dig_commands.append(f"dig TXT {exp.name}")
        elif exp.record_type == "DKIM":
            dig_commands.append(f"dig CNAME {exp.name}")
        elif exp.record_type == "DMARC":
            dig_commands.append(f"dig TXT {exp.name}")
    
    lines += [
        "",
        "## Manual Verification",
        "",
        "Run the following commands and compare with the expected values:",
        "",
        "```bash",
    ]
    lines.extend(dig_commands)
    lines += [
        "```",
        "",
        "*Status `VERIFIED` indicates DNS records match expectations. `UNVERIFIED` requires manual validation.*",
    ]

    return "\n".join(lines) + "\n"


def build_report(
    tenant_id: str,
    domain: str,
    provider: str | None = None,
    verify: bool = False,
    verbose: bool = False,
) -> dict[str, object]:
    expectations = build_expectations(domain, provider)
    
    if verify:
        if verbose:
            print(f"Verifying DNS records for {domain}...")
        expectations = [verify_expectation(exp, provider, verbose) for exp in expectations]
    
    # Determine overall status
    if verify:
        verified_count = sum(1 for exp in expectations if exp.status == "VERIFIED")
        total_count = len(expectations)
        overall_status = "VERIFIED" if verified_count == total_count else "PARTIAL" if verified_count > 0 else "UNVERIFIED"
    else:
        overall_status = "EXPECTED"
        verified_count = 0
        total_count = len(expectations)
    
    return {
        "tenant_id": tenant_id,
        "domain": domain,
        "provider": provider,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": overall_status,
        "verified_count": verified_count,
        "total_count": total_count,
        "records": [
            {
                "record_type": exp.record_type,
                "name": exp.name,
                "expected_value": exp.expected_value,
                "actual_value": exp.actual_value,
                "status": exp.status,
            }
            for exp in expectations
        ],
        "notes": [
            "Auto-verification enabled." if verify else "Log-only report. Use --verify to check DNS records.",
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
            actual_value=rec.get("actual_value"),
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
    parser.add_argument("--provider", choices=["brevo"], help="Email provider (determines expected patterns)")
    parser.add_argument("--verify", action="store_true", help="Perform real DNS lookups and verify")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    
    if args.verify and not args.provider:
        print("Error: --verify requires --provider to be specified", file=__import__("sys").stderr)
        return 1
    
    report = build_report(
        args.tenant,
        args.domain,
        provider=args.provider,
        verify=args.verify,
        verbose=args.verbose,
    )
    json_path, md_path = write_outputs(args.tenant, args.domain, report)
    
    summary = {
        "tenant_id": args.tenant,
        "domain": args.domain,
        "provider": args.provider,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "status": report["status"],
        "verified_count": report["verified_count"],
        "total_count": report["total_count"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    
    if args.verify:
        print(f"\nDNS verification complete: {report['verified_count']}/{report['total_count']} records verified.")
    else:
        print("\nDNS expectations written (use --verify to check DNS records).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

