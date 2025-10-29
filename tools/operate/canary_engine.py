"""Canary decision engine for Mahnwesen rollout gating."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


ARTIFACT_ROOT = Path("artifacts/reports/mahnwesen")
TZ_EUROPE_BERLIN = ZoneInfo("Europe/Berlin")


@dataclass
class Thresholds:
    error_rate: float = 0.02
    hard_bounce_rate: float = 0.05
    dlq_depth: int = 10
    retry_depth: int = 50
    min_notices: int = 3


def _tenant_env_key(tenant_id: str) -> str:
    return tenant_id.upper().replace("-", "_")


def load_thresholds(tenant_id: str) -> Thresholds:
    tenant_key = _tenant_env_key(tenant_id)

    def get_float(name: str, default: float) -> float:
        tenant_value = os.getenv(f"CANARY_THRESHOLD_{name}_{tenant_key}")
        if tenant_value is not None:
            try:
                return float(tenant_value)
            except ValueError:
                pass
        global_value = os.getenv(f"CANARY_THRESHOLD_{name}")
        if global_value is not None:
            try:
                return float(global_value)
            except ValueError:
                pass
        return default

    def get_int(name: str, default: int) -> int:
        tenant_value = os.getenv(f"CANARY_THRESHOLD_{name}_{tenant_key}")
        if tenant_value is not None and tenant_value.isdigit():
            return int(tenant_value)
        global_value = os.getenv(f"CANARY_THRESHOLD_{name}")
        if global_value is not None and global_value.isdigit():
            return int(global_value)
        return default

    return Thresholds(
        error_rate=get_float("ERROR_RATE", Thresholds.error_rate),
        hard_bounce_rate=get_float("HARD_BOUNCE_RATE", Thresholds.hard_bounce_rate),
        dlq_depth=get_int("DLQ_DEPTH", Thresholds.dlq_depth),
        retry_depth=get_int("RETRY_DEPTH", Thresholds.retry_depth),
        min_notices=get_int("MIN_NOTICES", Thresholds.min_notices),
    )


def load_kpi_metrics(tenant_id: str, report_date: date, base_path: Path = ARTIFACT_ROOT) -> dict[str, Any]:
    path = base_path / tenant_id / f"{report_date.isoformat()}.json"
    if not path.exists():
        raise FileNotFoundError(f"KPI report not found: {path}")
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    return data


def load_blocklist_stats(tenant_id: str, base_path: Path = ARTIFACT_ROOT) -> dict[str, Any]:
    blocklist_path = base_path / tenant_id / "ops" / "blocklist.json"
    hard = 0
    total = 0
    if blocklist_path.exists():
        with blocklist_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        entries = data.get("entries", {})
        for entry in entries.values():
            total += 1
            if str(entry.get("status", "")).lower() == "hard":
                hard += 1
    return {"hard": hard, "total": total}


def load_operate_state(tenant_id: str, base_path: Path = ARTIFACT_ROOT) -> dict[str, Any]:
    state_path = base_path / tenant_id / "operate" / "operate_state.json"
    if state_path.exists():
        with state_path.open("r", encoding="utf-8") as fp:
            try:
                data = json.load(fp)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}
    data.setdefault("rollout_percentage", 10)
    data.setdefault("kill_switch", False)
    return data


def determine_next_action(
    tenant_id: str,
    report_date: date,
    kpi: dict[str, Any],
    blocklist_stats: dict[str, Any],
    state: dict[str, Any],
    thresholds: Thresholds,
) -> dict[str, Any]:
    metrics = kpi.get("metrics", {})
    notices_sent = metrics.get("notices_sent", 0)
    hard_bounces = metrics.get("hard_bounces", 0)
    errors = metrics.get("errors", 0)
    retry_depth = metrics.get("retry_depth", 0)
    dlq_depth = metrics.get("dlq_depth", 0)

    hard_bounce_rate = hard_bounces / max(1, notices_sent)
    error_rate = errors / max(1, notices_sent)

    reasons: list[str] = []

    if notices_sent < thresholds.min_notices:
        reasons.append(
            f"Notices sent {notices_sent} below minimum {thresholds.min_notices}"
        )

    if error_rate > thresholds.error_rate:
        reasons.append(
            f"Error rate {error_rate:.3f} exceeds threshold {thresholds.error_rate:.3f}"
        )

    if hard_bounce_rate > thresholds.hard_bounce_rate:
        reasons.append(
            f"Hard bounce rate {hard_bounce_rate:.3f} exceeds threshold {thresholds.hard_bounce_rate:.3f}"
        )

    if dlq_depth > thresholds.dlq_depth:
        reasons.append(
            f"DLQ depth {dlq_depth} exceeds threshold {thresholds.dlq_depth}"
        )

    if retry_depth > thresholds.retry_depth:
        reasons.append(
            f"Retry depth {retry_depth} exceeds threshold {thresholds.retry_depth}"
        )

    blocklist_total = blocklist_stats.get("total", 0)
    blocklist_hard = blocklist_stats.get("hard", 0)
    blocklist_rate = blocklist_hard / max(1, blocklist_total)
    if blocklist_total > 0 and blocklist_rate > thresholds.hard_bounce_rate:
        reasons.append(
            f"Hard blocklist ratio {blocklist_rate:.3f} exceeds threshold {thresholds.hard_bounce_rate:.3f}"
        )

    current_pct = int(state.get("rollout_percentage", 10) or 10)

    progression = {10: "GO_25", 25: "GO_50", 50: "GO_100"}

    recommended: str
    action_notes: list[str] = []

    severe_error_threshold = max(thresholds.error_rate * 5, 0.2)
    severe_bounce_threshold = max(thresholds.hard_bounce_rate * 5, 0.25)
    severe = error_rate > severe_error_threshold or hard_bounce_rate > severe_bounce_threshold

    if severe:
        recommended = "BACKOUT"
        if not reasons:
            reasons.append("Severe threshold breach detected")
    elif reasons:
        recommended = "HOLD"
    else:
        recommended = progression.get(current_pct, "GO_100")
        if recommended == "GO_100" and current_pct >= 100:
            recommended = "HOLD"
            reasons.append("Tenant already at 100 % rollout")
        else:
            action_notes.append(f"Advance rollout to {recommended.split('_')[1]} %")

    decision = {
        "tenant_id": tenant_id,
        "report_date": report_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "current_percentage": current_pct,
        "recommended_action": recommended,
        "reasons": reasons or action_notes or ["Thresholds satisfied"],
        "metrics": {
            "error_rate": round(error_rate, 4),
            "hard_bounce_rate": round(hard_bounce_rate, 4),
            "notices_sent": notices_sent,
            "hard_bounces": hard_bounces,
            "errors": errors,
            "retry_depth": retry_depth,
            "dlq_depth": dlq_depth,
            "cycle_time_median_hours": metrics.get("cycle_time_median_hours"),
        },
        "blocklist": {
            "hard": blocklist_hard,
            "total": blocklist_total,
        },
        "thresholds": {
            "error_rate": thresholds.error_rate,
            "hard_bounce_rate": thresholds.hard_bounce_rate,
            "dlq_depth": thresholds.dlq_depth,
            "retry_depth": thresholds.retry_depth,
            "min_notices": thresholds.min_notices,
        },
    }

    return decision


def render_markdown(decision: dict[str, Any]) -> str:
    lines = [
        f"# Canary Decision — Tenant `{decision['tenant_id']}`",
        "",
        f"*Generated:* {decision['generated_at']}",
        f"*Report Date:* {decision['report_date']} (Europe/Berlin)",
        f"*Current Rollout:* {decision['current_percentage']} %",
        f"*Recommended Action:* **{decision['recommended_action']}**",
        "",
        "## Reasons",
    ]
    for reason in decision["reasons"]:
        lines.append(f"- {reason}")

    metrics = decision["metrics"]
    lines += [
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Error Rate | {metrics['error_rate']:.4f} |",
        f"| Hard Bounce Rate | {metrics['hard_bounce_rate']:.4f} |",
        f"| Notices Sent | {metrics['notices_sent']} |",
        f"| Hard Bounces | {metrics['hard_bounces']} |",
        f"| Errors | {metrics['errors']} |",
        f"| Retry Depth | {metrics['retry_depth']} |",
        f"| DLQ Depth | {metrics['dlq_depth']} |",
        f"| Cycle Time Median (h) | {metrics['cycle_time_median_hours']} |",
    ]

    blocklist = decision["blocklist"]
    lines += [
        "",
        "## Blocklist",
        "",
        f"Hard entries: {blocklist['hard']} / {max(1, blocklist['total'])} total",
        "",
        "## Manual Tasks",
        "",
        "- Review alerts and KPI anomalies",
        "- Update rollout percentage via `canary_rollout.py` if GO decision",
        "- Execute kill-switch if BACKOUT",
    ]

    return "\n".join(lines) + "\n"


def write_decision(
    tenant_id: str,
    decision: dict[str, Any],
    report_date: date,
    now: datetime,
    base_path: Path = ARTIFACT_ROOT,
) -> tuple[Path, Path]:
    canary_dir = base_path / tenant_id / "canary"
    canary_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y-%m-%d_%H%M")
    json_path = canary_dir / f"{timestamp}_decision.json"
    md_path = canary_dir / f"{timestamp}_decision.md"

    with json_path.open("w", encoding="utf-8") as fp:
        json.dump(decision, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    md_path.write_text(render_markdown(decision), encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate canary decision for Mahnwesen")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    parser.add_argument(
        "--date",
        help="Report date (YYYY-MM-DD) in Europe/Berlin timezone",
    )
    return parser.parse_args(argv)


def generate_decision(tenant_id: str, report_date: date, base_path: Path = ARTIFACT_ROOT) -> dict[str, Any]:
    kpi = load_kpi_metrics(tenant_id, report_date, base_path=base_path)
    blocklist_stats = load_blocklist_stats(tenant_id, base_path=base_path)
    state = load_operate_state(tenant_id, base_path=base_path)
    thresholds = load_thresholds(tenant_id)
    return determine_next_action(tenant_id, report_date, kpi, blocklist_stats, state, thresholds)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.date:
        report_date = date.fromisoformat(args.date)
    else:
        report_date = datetime.now(TZ_EUROPE_BERLIN).date()

    decision = generate_decision(args.tenant, report_date)
    now = datetime.now(UTC)
    json_path, md_path = write_decision(args.tenant, decision, report_date, now)

    output = {
        "tenant_id": args.tenant,
        "report_date": report_date.isoformat(),
        "decision": decision["recommended_action"],
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "reasons": decision["reasons"],
    }
    print(json.dumps(output, ensure_ascii=False))
    print(f"Decision: {decision['recommended_action']} — reasons: {', '.join(decision['reasons'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

