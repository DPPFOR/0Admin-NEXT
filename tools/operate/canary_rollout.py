"""Rollout controller applying canary decisions."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ARTIFACT_ROOT = Path("artifacts/reports/mahnwesen")


def load_operate_state(tenant_id: str, base_path: Path = ARTIFACT_ROOT) -> tuple[Path, dict[str, Any]]:
    operate_dir = base_path / tenant_id / "operate"
    operate_dir.mkdir(parents=True, exist_ok=True)
    state_path = operate_dir / "operate_state.json"
    if state_path.exists():
        with state_path.open("r", encoding="utf-8") as fp:
            try:
                state = json.load(fp)
            except json.JSONDecodeError:
                state = {}
    else:
        state = {}
    state.setdefault("kill_switch", False)
    state.setdefault("rollout_percentage", 10)
    return state_path, state


def persist_state(state_path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(UTC).isoformat()
    with state_path.open("w", encoding="utf-8") as fp:
        json.dump(state, fp, indent=2, ensure_ascii=False)
        fp.write("\n")


def load_decision(tenant_id: str, decision_path: str | None, base_path: Path = ARTIFACT_ROOT) -> tuple[Path, dict[str, Any]]:
    if decision_path:
        decision_file = Path(decision_path)
    else:
        canary_dir = base_path / tenant_id / "canary"
        if not canary_dir.exists():
            raise FileNotFoundError(f"No canary decisions found for tenant {tenant_id}")
        decision_file = max(canary_dir.glob("*_decision.json"), default=None)
        if decision_file is None:
            raise FileNotFoundError(f"No canary decisions found for tenant {tenant_id}")

    with decision_file.open("r", encoding="utf-8") as fp:
        decision = json.load(fp)
    return decision_file, decision


def determine_target_percentage(current: int, action: str) -> int:
    mapping = {
        "GO_25": 25,
        "GO_50": 50,
        "GO_100": 100,
    }
    return mapping.get(action, current)


def apply_rollout(
    tenant_id: str,
    decision: dict[str, Any],
    trace_id: str,
    base_path: Path = ARTIFACT_ROOT,
) -> dict[str, Any]:
    state_path, state = load_operate_state(tenant_id, base_path=base_path)
    before_state = {
        "kill_switch": state.get("kill_switch", False),
        "rollout_percentage": state.get("rollout_percentage", 10),
    }

    action = decision.get("recommended_action", "HOLD")
    reasons = decision.get("reasons", [])
    changed = False

    if action == "BACKOUT":
        reason_text = ", ".join(reasons) if reasons else "Backout requested"
        # Apply kill switch and set rollout to baseline (10 %)
        state["kill_switch"] = True
        state["kill_switch_reason"] = reason_text
        state["kill_switch_trace_id"] = trace_id
        state["rollout_percentage"] = min(state.get("rollout_percentage", 10), 10)
        changed = True
    elif action.startswith("GO_"):
        target_pct = determine_target_percentage(int(state.get("rollout_percentage", 10)), action)
        if state.get("rollout_percentage", 10) < target_pct:
            state["rollout_percentage"] = target_pct
            state["kill_switch"] = False
            state.pop("kill_switch_reason", None)
            state.pop("kill_switch_trace_id", None)
            state.pop("reason", None)
            state.pop("trace_id", None)
            changed = True
    # HOLD or unrecognised actions leave state unchanged

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "trace_id": trace_id,
        "decision": action,
        "before": before_state,
        "after": {
            "kill_switch": state.get("kill_switch", False),
            "rollout_percentage": state.get("rollout_percentage", 10),
        },
        "changed": changed,
        "reasons": reasons,
    }

    history = state.setdefault("history", [])
    history.append(entry)

    persist_state(state_path, state)

    canary_dir = (base_path / tenant_id / "canary")
    canary_dir.mkdir(parents=True, exist_ok=True)
    log_path = canary_dir / f"{datetime.now(UTC).strftime('%Y-%m-%d_%H%M%S')}_rollout_log.json"
    with log_path.open("w", encoding="utf-8") as fp:
        json.dump(entry, fp, indent=2, ensure_ascii=False)
        fp.write("\n")

    return {
        "state_path": str(state_path),
        "log_path": str(log_path),
        "changed": changed,
        "after": entry["after"],
        "decision": action,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply canary rollout decision")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    parser.add_argument("--decision-file", help="Path to decision JSON (defaults to latest)")
    parser.add_argument("--trace-id", help="Trace identifier for the rollout event")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    trace_id = args.trace_id or str(uuid.uuid4())

    _, decision = load_decision(args.tenant, args.decision_file)
    result = apply_rollout(args.tenant, decision, trace_id)

    print(json.dumps(result, ensure_ascii=False))
    print(
        f"Rollout action={result['decision']} changed={result['changed']} "
        f"new_percentage={result['after']['rollout_percentage']} kill_switch={result['after']['kill_switch']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

