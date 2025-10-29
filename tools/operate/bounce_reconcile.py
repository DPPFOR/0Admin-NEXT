"""Bounce reconciliation for Mahnwesen Operate.

Rules:
* Hard bounces are blocked immediately.
* Soft bounces allow 3 attempts in 72 hours. Afterwards they are
  promoted to hard.
* The reconcile job is idempotent by tracking processed event IDs.

Artefacts live under ``artifacts/reports/mahnwesen/<tenant>/ops``.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List

from tools.operate.notifiers import NotificationPayload, emit_stdout, maybe_emit_slack

ARTIFACT_ROOT = Path("artifacts/reports/mahnwesen")
ROLLING_WINDOW = timedelta(hours=72)


@dataclass
class BounceEvent:
    event_id: str
    recipient_hash: str
    bounce_type: str
    occurred_at: datetime
    notice_id: str | None = None
    stage: str | None = None
    reason: str | None = None


@dataclass
class BlocklistEntry:
    status: str
    attempt_timestamps: List[str] = field(default_factory=list)
    last_event_at: str | None = None
    last_reason: str | None = None
    last_notice_id: str | None = None
    last_stage: str | None = None
    promoted_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "attempt_timestamps": self.attempt_timestamps,
            "last_event_at": self.last_event_at,
            "last_reason": self.last_reason,
            "last_notice_id": self.last_notice_id,
            "last_stage": self.last_stage,
            "promoted_at": self.promoted_at,
        }


@dataclass
class BounceResult:
    tenant_id: str
    processed: List[str]
    actions: List[dict[str, object]]
    blocklist_path: Path
    log_path: Path


class BounceReconciler:
    def __init__(self, tenant_id: str, base_path: Path | None = None) -> None:
        self.tenant_id = tenant_id
        self.base_path = base_path or ARTIFACT_ROOT
        self.tenant_ops = self.base_path / tenant_id / "ops"
        self.tenant_ops.mkdir(parents=True, exist_ok=True)

    def _load_json(self, path: Path, default: dict[str, object]) -> dict[str, object]:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_events(self) -> tuple[list[BounceEvent], set[str]]:
        inbox_file = self.tenant_ops / "bounce_inbox.json"
        data = self._load_json(inbox_file, {"events": []})
        events: list[BounceEvent] = []
        for raw in data.get("events", []):
            occurred = datetime.fromisoformat(raw["occurred_at"].replace("Z", "+00:00"))
            events.append(
                BounceEvent(
                    event_id=str(raw["event_id"]),
                    recipient_hash=str(raw["recipient_hash"]),
                    bounce_type=str(raw.get("bounce_type", "soft")).lower(),
                    occurred_at=occurred,
                    notice_id=raw.get("notice_id"),
                    stage=raw.get("stage"),
                    reason=raw.get("reason"),
                )
            )

        processed_file = self.tenant_ops / "bounce_processed.json"
        processed = self._load_json(processed_file, {"events": []})
        return events, set(processed.get("events", []))

    def _load_blocklist(self) -> Dict[str, BlocklistEntry]:
        blocklist_file = self.tenant_ops / "blocklist.json"
        raw = self._load_json(blocklist_file, {"entries": {}, "version": 1})
        entries: Dict[str, BlocklistEntry] = {}
        for recipient, data in raw.get("entries", {}).items():
            entries[recipient] = BlocklistEntry(
                status=str(data.get("status", "soft")),
                attempt_timestamps=list(data.get("attempt_timestamps", [])),
                last_event_at=data.get("last_event_at"),
                last_reason=data.get("last_reason"),
                last_notice_id=data.get("last_notice_id"),
                last_stage=data.get("last_stage"),
                promoted_at=data.get("promoted_at"),
            )
        return entries

    def process(self, dry_run: bool = False) -> BounceResult:
        events, processed_ids = self._load_events()
        blocklist = self._load_blocklist()

        actions: list[dict[str, object]] = []
        newly_processed: list[str] = []

        for event in events:
            if event.event_id in processed_ids:
                continue

            entry = blocklist.setdefault(event.recipient_hash, BlocklistEntry(status="soft"))
            timestamps = [
                ts
                for ts in entry.attempt_timestamps
                if datetime.fromisoformat(ts.replace("Z", "+00:00")) >= event.occurred_at - ROLLING_WINDOW
            ]
            entry.attempt_timestamps = timestamps

            event_iso = event.occurred_at.isoformat()
            entry.last_event_at = event_iso
            entry.last_reason = event.reason
            entry.last_notice_id = event.notice_id
            entry.last_stage = event.stage

            action_type = "record_soft"

            if event.bounce_type == "hard":
                entry.status = "hard"
                entry.attempt_timestamps.append(event_iso)
                entry.promoted_at = entry.promoted_at or event_iso
                action_type = "block_hard"
            else:
                entry.attempt_timestamps.append(event_iso)
                if len(entry.attempt_timestamps) >= 3:
                    entry.status = "hard"
                    entry.promoted_at = event_iso
                    action_type = "promote_hard"
                else:
                    entry.status = "soft"

            actions.append(
                {
                    "recipient_hash": event.recipient_hash,
                    "action": action_type,
                    "event_id": event.event_id,
                    "attempts": len(entry.attempt_timestamps),
                    "status": entry.status,
                    "reason": event.reason,
                    "occurred_at": event_iso,
                }
            )

            newly_processed.append(event.event_id)

        timestamp = datetime.now(UTC)
        log_path = self.tenant_ops / f"bounce_reconcile_{timestamp.isoformat().replace(':', '')}.json"
        blocklist_path = self.tenant_ops / "blocklist.json"

        modified = bool(newly_processed)

        if not dry_run:
            if modified:
                payload = {
                    "version": 1,
                    "updated_at": timestamp.isoformat(),
                    "entries": {r: entry.to_dict() for r, entry in blocklist.items()},
                }
                blocklist_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

                processed_file = self.tenant_ops / "bounce_processed.json"
                processed_ids.update(newly_processed)
                processed_file.write_text(
                    json.dumps({"events": sorted(processed_ids)}, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

                inbox_file = self.tenant_ops / "bounce_inbox.json"
                remaining = [evt for evt in events if evt.event_id not in processed_ids]
                inbox_file.write_text(
                    json.dumps({"events": [self._event_to_dict(evt) for evt in remaining]}, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

            log_payload = {
                "tenant_id": self.tenant_id,
                "timestamp": timestamp.isoformat(),
                "actions": actions,
                "processed_event_ids": newly_processed,
            }
            log_path.write_text(json.dumps(log_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            log_path = Path("/dev/null")

        return BounceResult(
            tenant_id=self.tenant_id,
            processed=newly_processed,
            actions=actions,
            blocklist_path=blocklist_path,
            log_path=log_path,
        )

    def _event_to_dict(self, event: BounceEvent) -> dict[str, object]:
        return {
            "event_id": event.event_id,
            "recipient_hash": event.recipient_hash,
            "bounce_type": event.bounce_type,
            "occurred_at": event.occurred_at.isoformat(),
            "notice_id": event.notice_id,
            "stage": event.stage,
            "reason": event.reason,
        }


def discover_tenants(base_path: Path = ARTIFACT_ROOT) -> list[str]:
    if not base_path.exists():
        return []
    return sorted([p.name for p in base_path.iterdir() if p.is_dir()])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile bounce events for Mahnwesen")
    parser.add_argument("--tenant", help="Tenant UUID")
    parser.add_argument("--all-tenants", action="store_true", help="Process all tenants")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist changes")
    parser.add_argument("--notify", action="store_true", help="Emit notification output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.tenant and args.all_tenants:
        raise SystemExit("--tenant and --all-tenants cannot be combined")

    if args.all_tenants:
        tenants: Iterable[str] = discover_tenants()
    else:
        tenant = args.tenant or os.environ.get("TENANT_DEFAULT")
        if not tenant:
            raise SystemExit("TENANT_DEFAULT not set and no --tenant specified")
        tenants = [tenant]

    for tenant_id in tenants:
        reconciler = BounceReconciler(tenant_id)
        result = reconciler.process(dry_run=args.dry_run)

        payload = NotificationPayload(
            title=f"Bounce reconcile {tenant_id}",
            message=f"Processed {len(result.processed)} events, actions={len(result.actions)}",
            details={
                "tenant_id": tenant_id,
                "processed_event_ids": result.processed,
                "actions": result.actions,
                "blocklist_path": str(result.blocklist_path),
                "log_path": str(result.log_path),
            },
        )

        if args.notify:
            slack_sent = maybe_emit_slack(payload)
            if not slack_sent:
                emit_stdout(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

