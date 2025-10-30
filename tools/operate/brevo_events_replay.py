"""Replay tool for Brevo events from NDJSON files."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from agents.comm.event_sink import EventSink
from agents.comm.events import CommEvent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Replay Brevo events from NDJSON files")
    parser.add_argument("--tenant", required=True, help="Tenant ID (UUID)")
    parser.add_argument("--date", help="Date filter (YYYYMMDD)", default=None)
    parser.add_argument("--type", help="Event type filter", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode (no persistence)")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("artifacts") / "events",
        help="Base directory for events (default: artifacts/events)",
    )
    return parser.parse_args(argv)


def load_events_from_ndjson(ndjson_file: Path) -> list[dict]:
    """Load events from NDJSON file.

    Args:
        ndjson_file: Path to NDJSON file

    Returns:
        List of event dictionaries
    """
    if not ndjson_file.exists():
        return []

    events = []
    for line in ndjson_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            events.append(event)
        except json.JSONDecodeError as e:
            print(f"WARNING: Skipping invalid JSON line: {e}", file=sys.stderr)
            continue

    return events


def filter_events(events: list[dict], event_type: str | None = None, date_str: str | None = None) -> list[dict]:
    """Filter events by type and date.

    Args:
        events: List of event dictionaries
        event_type: Event type filter (optional)
        date_str: Date filter YYYYMMDD (optional)

    Returns:
        Filtered list of events
    """
    filtered = events

    if event_type:
        filtered = [e for e in filtered if e.get("event_type") == event_type]

    if date_str:
        filtered = [
            e
            for e in filtered
            if e.get("ts") and datetime.fromisoformat(e["ts"].replace("Z", "+00:00")).strftime("%Y%m%d") == date_str
        ]

    return filtered


def replay_event(event_dict: dict, tenant_id: str, dry_run: bool = False) -> tuple[bool, str]:
    """Replay a single event.

    Args:
        event_dict: Event dictionary
        tenant_id: Tenant ID
        dry_run: If True, don't persist

    Returns:
        Tuple (success, message)
    """
    if dry_run:
        return True, f"DRY-RUN: Would replay {event_dict.get('event_type')} event"

    try:
        # Reconstruct CommEvent from dict
        comm_event = CommEvent(
            event_type=event_dict.get("event_type", "unknown"),
            tenant_id=tenant_id,
            message_id=event_dict.get("message_id"),
            recipient=event_dict.get("recipient"),
            reason=event_dict.get("reason"),
            ts=datetime.fromisoformat(event_dict["ts"].replace("Z", "+00:00")),
            metadata=event_dict.get("metadata", {}),
            provider=event_dict.get("provider", "brevo"),
            provider_event_id=event_dict.get("provider_event_id"),
        )

        # Persist event
        event_sink = EventSink()
        was_persisted, event_file = event_sink.persist(comm_event)

        if was_persisted:
            return True, f"Replayed {comm_event.event_type} event -> {event_file}"
        else:
            return False, f"Skipped duplicate {comm_event.event_type} event (idempotency)"

    except Exception as e:
        return False, f"Error replaying event: {str(e)}"


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    args = parse_args(argv)

    tenant_dir = args.base_dir / args.tenant

    if not tenant_dir.exists():
        print(f"ERROR: Tenant directory not found: {tenant_dir}", file=sys.stderr)
        sys.exit(1)

    # Find NDJSON files
    ndjson_files = []
    if args.date:
        # Specific date
        date_dir = tenant_dir / args.date
        if date_dir.exists():
            ndjson_file = date_dir / "events.ndjson"
            if ndjson_file.exists():
                ndjson_files.append(ndjson_file)
    else:
        # All dates
        for date_dir in sorted(tenant_dir.iterdir()):
            if date_dir.is_dir():
                ndjson_file = date_dir / "events.ndjson"
                if ndjson_file.exists():
                    ndjson_files.append(ndjson_file)

    if not ndjson_files:
        print(f"ERROR: No NDJSON files found for tenant {args.tenant}", file=sys.stderr)
        sys.exit(1)

    # Load and filter events
    all_events = []
    for ndjson_file in ndjson_files:
        events = load_events_from_ndjson(ndjson_file)
        all_events.extend(events)

    filtered_events = filter_events(all_events, event_type=args.type, date_str=args.date)

    if not filtered_events:
        print(f"INFO: No events found matching filters (type={args.type}, date={args.date})")
        return

    print(f"Found {len(filtered_events)} events to replay")
    if args.dry_run:
        print("DRY-RUN mode: No events will be persisted")

    # Replay events
    success_count = 0
    error_count = 0
    duplicate_count = 0

    for event_dict in filtered_events:
        success, message = replay_event(event_dict, args.tenant, dry_run=args.dry_run)
        print(message)

        if success:
            if "duplicate" in message.lower():
                duplicate_count += 1
            else:
                success_count += 1
        else:
            error_count += 1

    # Summary
    print(f"\nSummary:")
    print(f"  Replayed: {success_count}")
    print(f"  Duplicates (skipped): {duplicate_count}")
    print(f"  Errors: {error_count}")


if __name__ == "__main__":  # pragma: no cover
    main()

