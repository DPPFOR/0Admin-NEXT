"""Tests for event dispatch - offline.

Tests the outbox event publishing and idempotency
without external dependencies.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from agents.mahnwesen.clients import OutboxClient
from agents.mahnwesen.config import DunningConfig
from agents.mahnwesen.dto import DunningChannel, DunningEvent, DunningStage


class TestEventDispatch:
    """Test event dispatch and outbox publishing."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return DunningConfig(tenant_id="00000000-0000-0000-0000-000000000001")

    @pytest.fixture
    def outbox_client(self, config):
        """Create outbox client."""
        return OutboxClient(config)

    @pytest.fixture
    def sample_event(self):
        """Create sample dunning event."""
        return DunningEvent(
            event_id="EVENT-001",
            tenant_id="00000000-0000-0000-0000-000000000001",
            event_type="DUNNING_ISSUED",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            notice_ref="NOTICE-001",
            due_date=datetime.now(UTC) - timedelta(days=5),
            amount_cents=15000,
            correlation_id="CORR-001",
            schema_version="v1",
        )

    def test_idempotency_key_generation(self, outbox_client):
        """Test idempotency key generation."""
        tenant_id = "00000000-0000-0000-0000-000000000001"
        invoice_id = "INV-001"
        stage = DunningStage.STAGE_1

        key1 = outbox_client._generate_idempotency_key(tenant_id, invoice_id, stage)
        key2 = outbox_client._generate_idempotency_key(tenant_id, invoice_id, stage)

        # Should be deterministic
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex length
        assert key1.isalnum()

    def test_idempotency_key_different_inputs(self, outbox_client):
        """Test idempotency key with different inputs."""
        tenant_id = "00000000-0000-0000-0000-000000000001"
        invoice_id = "INV-001"
        stage = DunningStage.STAGE_1

        key1 = outbox_client._generate_idempotency_key(tenant_id, invoice_id, stage)

        # Different tenant
        key2 = outbox_client._generate_idempotency_key(
            "00000000-0000-0000-0000-000000000002", invoice_id, stage
        )
        assert key1 != key2

        # Different invoice
        key3 = outbox_client._generate_idempotency_key(tenant_id, "INV-002", stage)
        assert key1 != key3

        # Different stage
        key4 = outbox_client._generate_idempotency_key(tenant_id, invoice_id, DunningStage.STAGE_2)
        assert key1 != key4

    def test_idempotency_key_normalization(self, outbox_client):
        """Test idempotency key normalization."""
        # Test with whitespace and case variations
        key1 = outbox_client._generate_idempotency_key(
            " 00000000-0000-0000-0000-000000000001 ", "INV-001", DunningStage.STAGE_1
        )
        key2 = outbox_client._generate_idempotency_key(
            "00000000-0000-0000-0000-000000000001", "INV-001", DunningStage.STAGE_1
        )

        # Should be the same after normalization
        assert key1 == key2

    def test_outbox_payload_creation(self, outbox_client, sample_event):
        """Test outbox payload creation."""
        idempotency_key = "test-key-123"

        payload = outbox_client._create_outbox_payload(sample_event, idempotency_key)

        # Check payload structure
        assert payload["tenant_id"] == sample_event.tenant_id
        assert payload["event_type"] == sample_event.event_type
        assert payload["idempotency_key"] == idempotency_key
        assert payload["schema_version"] == sample_event.schema_version
        assert payload["status"] == "pending"
        assert payload["retry_count"] == 0

        # Check payload_json
        payload_json = payload["payload_json"]
        assert payload_json["event_id"] == sample_event.event_id
        assert payload_json["tenant_id"] == sample_event.tenant_id
        assert payload_json["invoice_id"] == sample_event.invoice_id
        assert payload_json["stage"] == sample_event.stage.value
        assert payload_json["channel"] == sample_event.channel.value

    def test_publish_dunning_issued_success(self, outbox_client, sample_event):
        """Test successful dunning issued event publishing."""
        with patch.object(outbox_client, "_simulate_outbox_write") as mock_write:
            result = outbox_client.publish_dunning_issued(sample_event, "CORR-001")

            assert result is True
            mock_write.assert_called_once()

    def test_publish_dunning_issued_failure(self, outbox_client, sample_event):
        """Test dunning issued event publishing failure."""
        with patch.object(
            outbox_client, "_simulate_outbox_write", side_effect=Exception("DB Error")
        ):
            result = outbox_client.publish_dunning_issued(sample_event, "CORR-001")

            assert result is False

    def test_publish_dunning_escalated_success(self, outbox_client, sample_event):
        """Test successful dunning escalated event publishing."""
        from_stage = DunningStage.STAGE_1
        reason = "Payment deadline exceeded"

        with patch.object(outbox_client, "_simulate_outbox_write") as mock_write:
            result = outbox_client.publish_dunning_escalated(
                sample_event, from_stage, reason, "CORR-001"
            )

            assert result is True
            mock_write.assert_called_once()

            # Check that escalation data was added
            call_args = mock_write.call_args[0][0]
            payload_json = call_args["payload_json"]
            assert payload_json["from_stage"] == from_stage.value
            assert payload_json["reason"] == reason
            assert "escalated_at" in payload_json

    def test_publish_dunning_resolved_success(self, outbox_client, sample_event):
        """Test successful dunning resolved event publishing."""
        resolution = "Payment received"
        resolved_at = datetime.now(UTC)

        with patch.object(outbox_client, "_simulate_outbox_write") as mock_write:
            result = outbox_client.publish_dunning_resolved(
                sample_event, resolution, resolved_at, "CORR-001"
            )

            assert result is True
            mock_write.assert_called_once()

            # Check that resolution data was added
            call_args = mock_write.call_args[0][0]
            payload_json = call_args["payload_json"]
            assert payload_json["resolution"] == resolution
            assert payload_json["resolved_at"] == resolved_at.isoformat()

    def test_check_duplicate_event(self, outbox_client):
        """Test duplicate event checking."""
        tenant_id = "00000000-0000-0000-0000-000000000001"
        invoice_id = "INV-001"
        stage = DunningStage.STAGE_1

        # Should return False for testing (no duplicates)
        result = outbox_client.check_duplicate_event(tenant_id, invoice_id, stage)
        assert result is False

    def test_event_to_outbox_payload(self, sample_event):
        """Test event to outbox payload conversion."""
        payload = sample_event.to_outbox_payload()

        # Check required fields
        assert payload["event_id"] == sample_event.event_id
        assert payload["tenant_id"] == sample_event.tenant_id
        assert payload["invoice_id"] == sample_event.invoice_id
        assert payload["stage"] == sample_event.stage.value
        assert payload["channel"] == sample_event.channel.value
        assert payload["notice_ref"] == sample_event.notice_ref
        assert payload["correlation_id"] == sample_event.correlation_id

        # Check amount formatting
        assert payload["amount"] == "150.00"  # 15000 cents / 100

    def test_event_serialization(self, sample_event):
        """Test event serialization to dictionary."""
        data = sample_event.to_dict()

        # Check all fields are present
        assert data["event_id"] == sample_event.event_id
        assert data["tenant_id"] == sample_event.tenant_id
        assert data["event_type"] == sample_event.event_type
        assert data["invoice_id"] == sample_event.invoice_id
        assert data["stage"] == sample_event.stage.value
        assert data["channel"] == sample_event.channel.value
        assert data["notice_ref"] == sample_event.notice_ref
        assert data["amount_cents"] == sample_event.amount_cents
        assert data["correlation_id"] == sample_event.correlation_id
        assert data["schema_version"] == sample_event.schema_version

    def test_event_deserialization(self, sample_event):
        """Test event deserialization from dictionary."""
        data = sample_event.to_dict()

        # Create new event from data
        new_event = DunningEvent.from_dict(data)

        # Check all fields match
        assert new_event.event_id == sample_event.event_id
        assert new_event.tenant_id == sample_event.tenant_id
        assert new_event.event_type == sample_event.event_type
        assert new_event.invoice_id == sample_event.invoice_id
        assert new_event.stage == sample_event.stage
        assert new_event.channel == sample_event.channel
        assert new_event.notice_ref == sample_event.notice_ref
        assert new_event.amount_cents == sample_event.amount_cents
        assert new_event.correlation_id == sample_event.correlation_id
        assert new_event.schema_version == sample_event.schema_version

    def test_event_types(self):
        """Test different event types."""
        event_types = ["DUNNING_ISSUED", "DUNNING_ESCALATED", "DUNNING_RESOLVED"]

        for event_type in event_types:
            event = DunningEvent(
                event_id="EVENT-TEST",
                tenant_id="00000000-0000-0000-0000-000000000001",
                event_type=event_type,
                invoice_id="INV-001",
                stage=DunningStage.STAGE_1,
                channel=DunningChannel.EMAIL,
                notice_ref="NOTICE-001",
            )

            assert event.event_type == event_type
            assert event.to_dict()["event_type"] == event_type

    def test_schema_version_handling(self):
        """Test schema version handling."""
        event = DunningEvent(
            event_id="EVENT-TEST",
            tenant_id="00000000-0000-0000-0000-000000000001",
            event_type="DUNNING_ISSUED",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            notice_ref="NOTICE-001",
            schema_version="v2",
        )

        assert event.schema_version == "v2"
        assert event.to_dict()["schema_version"] == "v2"

    def test_correlation_id_handling(self):
        """Test correlation ID handling."""
        event = DunningEvent(
            event_id="EVENT-TEST",
            tenant_id="00000000-0000-0000-0000-000000000001",
            event_type="DUNNING_ISSUED",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            notice_ref="NOTICE-001",
            correlation_id="CORR-TEST-123",
        )

        assert event.correlation_id == "CORR-TEST-123"
        assert event.to_dict()["correlation_id"] == "CORR-TEST-123"

    def test_payload_handling(self):
        """Test custom payload handling."""
        custom_payload = {"custom_field": "custom_value", "metadata": {"key": "value"}}

        event = DunningEvent(
            event_id="EVENT-TEST",
            tenant_id="00000000-0000-0000-0000-000000000001",
            event_type="DUNNING_ISSUED",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            notice_ref="NOTICE-001",
            payload=custom_payload,
        )

        assert event.payload == custom_payload
        assert event.to_dict()["payload"] == custom_payload

    @pytest.mark.parametrize(
        "stage,expected_stage_value",
        [
            (DunningStage.STAGE_1, 1),
            (DunningStage.STAGE_2, 2),
            (DunningStage.STAGE_3, 3),
        ],
    )
    def test_stage_serialization(self, stage, expected_stage_value):
        """Test stage serialization."""
        event = DunningEvent(
            event_id="EVENT-TEST",
            tenant_id="00000000-0000-0000-0000-000000000001",
            event_type="DUNNING_ISSUED",
            invoice_id="INV-001",
            stage=stage,
            channel=DunningChannel.EMAIL,
            notice_ref="NOTICE-001",
        )

        assert event.to_dict()["stage"] == expected_stage_value
        assert event.to_outbox_payload()["stage"] == expected_stage_value

    @pytest.mark.parametrize(
        "channel,expected_channel_value",
        [
            (DunningChannel.EMAIL, "email"),
            (DunningChannel.LETTER, "letter"),
            (DunningChannel.SMS, "sms"),
        ],
    )
    def test_channel_serialization(self, channel, expected_channel_value):
        """Test channel serialization."""
        event = DunningEvent(
            event_id="EVENT-TEST",
            tenant_id="00000000-0000-0000-0000-000000000001",
            event_type="DUNNING_ISSUED",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=channel,
            notice_ref="NOTICE-001",
        )

        assert event.to_dict()["channel"] == expected_channel_value
        assert event.to_outbox_payload()["channel"] == expected_channel_value
