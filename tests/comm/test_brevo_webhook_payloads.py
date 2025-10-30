"""Tests for Brevo webhook payload mapping and persistence."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from agents.comm.brevo_schema import parse_brevo_event
from agents.comm.event_sink import EventSink
from agents.comm.events import BrevoEventMapper


@pytest.fixture
def fixtures_dir():
    """Fixture directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def event_sink():
    """Event sink with temporary directory."""
    with TemporaryDirectory() as tmpdir:
        sink = EventSink(base_dir=Path(tmpdir))
        yield sink


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize(
    "event_file,event_type",
    [
        ("delivered.json", "delivered"),
        ("soft_bounce.json", "soft_bounce"),
        ("hard_bounce.json", "hard_bounce"),
        ("blocked.json", "blocked"),
        ("spam.json", "spam"),
        ("invalid.json", "invalid"),
        ("opened.json", "opened"),
        ("click.json", "click"),
    ],
)
def test_parse_brevo_event(fixtures_dir, event_file, event_type):
    """Test parsing Brevo events from fixtures."""
    fixture_path = fixtures_dir / event_file
    if not fixture_path.exists():
        pytest.skip(f"Fixture {event_file} not found")

    payload = json.loads(fixture_path.read_text())
    brevo_event = parse_brevo_event(payload)

    assert brevo_event.event.lower() == event_type


@pytest.mark.parametrize(
    "event_file,event_type",
    [
        ("delivered.json", "delivered"),
        ("soft_bounce.json", "soft_bounce"),
        ("hard_bounce.json", "hard_bounce"),
        ("blocked.json", "blocked"),
        ("spam.json", "spam"),
        ("invalid.json", "invalid"),
    ],
)
def test_map_to_comm_event(fixtures_dir, event_file, event_type, tenant_id):
    """Test mapping Brevo events to normalized CommEvent."""
    fixture_path = fixtures_dir / event_file
    if not fixture_path.exists():
        pytest.skip(f"Fixture {event_file} not found")

    payload = json.loads(fixture_path.read_text())
    brevo_event = parse_brevo_event(payload)

    comm_event = BrevoEventMapper.map_to_comm_event(
        brevo_event, tenant_id, provider_event_id="test-123"
    )

    assert comm_event.event_type == event_type
    assert comm_event.tenant_id == tenant_id
    assert comm_event.provider == "brevo"
    assert comm_event.provider_event_id == "test-123"
    assert comm_event.message_id is not None


def test_persist_event(event_sink, tenant_id, fixtures_dir):
    """Test event persistence."""
    fixture_path = fixtures_dir / "delivered.json"
    payload = json.loads(fixture_path.read_text())
    brevo_event = parse_brevo_event(payload)

    comm_event = BrevoEventMapper.map_to_comm_event(brevo_event, tenant_id)

    was_persisted, event_file = event_sink.persist(comm_event)

    assert was_persisted is True
    assert event_file is not None
    assert event_file.exists()

    # Verify event file content
    event_data = json.loads(event_file.read_text())
    assert event_data["event_type"] == "delivered"
    assert event_data["tenant_id"] == tenant_id
    assert event_data["event_id"] is not None
    assert event_data["idempotency_key"] is not None

    # Verify NDJSON file exists
    date_str = comm_event.ts.strftime("%Y%m%d")
    ndjson_file = event_sink.base_dir / tenant_id / date_str / "events.ndjson"
    assert ndjson_file.exists()

    # Verify NDJSON content
    lines = ndjson_file.read_text().strip().split("\n")
    assert len(lines) == 1
    ndjson_event = json.loads(lines[0])
    assert ndjson_event["event_type"] == "delivered"


def test_idempotency(event_sink, tenant_id, fixtures_dir):
    """Test idempotency - duplicate events should be dropped."""
    fixture_path = fixtures_dir / "delivered.json"
    payload = json.loads(fixture_path.read_text())
    brevo_event = parse_brevo_event(payload)

    # Add provider_event_id for idempotency testing
    comm_event1 = BrevoEventMapper.map_to_comm_event(
        brevo_event, tenant_id, provider_event_id="test-123"
    )
    comm_event2 = BrevoEventMapper.map_to_comm_event(
        brevo_event, tenant_id, provider_event_id="test-123"
    )

    # First persistence should succeed
    was_persisted1, event_file1 = event_sink.persist(comm_event1)
    assert was_persisted1 is True

    # Second persistence should be dropped (idempotency)
    was_persisted2, event_file2 = event_sink.persist(comm_event2)
    assert was_persisted2 is False
    assert event_file2 is None


def test_extract_tenant_id_from_header():
    """Test tenant ID extraction from header."""
    payload = {}
    tenant_header = "00000000-0000-0000-0000-000000000001"

    tenant_id = BrevoEventMapper.extract_tenant_id(payload, tenant_header)
    assert tenant_id == tenant_header


def test_extract_tenant_id_from_metadata():
    """Test tenant ID extraction from payload metadata."""
    payload = {"metadata": {"tenant_id": "00000000-0000-0000-0000-000000000002"}}
    tenant_id = BrevoEventMapper.extract_tenant_id(payload, None)
    assert tenant_id == "00000000-0000-0000-0000-000000000002"


def test_extract_tenant_id_fallback_default():
    """Test tenant ID extraction fallback to default."""
    payload = {}
    tenant_id = BrevoEventMapper.extract_tenant_id(payload, None)
    assert tenant_id is None

