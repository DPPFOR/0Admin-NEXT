"""Tests for Brevo email adapter."""

import os
from unittest.mock import Mock, patch

from backend.integrations.brevo_client import BrevoClient, BrevoResponse, send_transactional


class TestBrevoAdapter:
    """Test Brevo email adapter."""

    def test_brevo_client_initialization(self):
        """Test Brevo client initialization."""
        with patch.dict(
            os.environ,
            {
                "BREVO_API_KEY": "test-key",
                "BREVO_SENDER_EMAIL": "test@example.com",
                "BREVO_SENDER_NAME": "Test Sender",
            },
        ):
            client = BrevoClient()

            assert client.api_key == "test-key"
            assert client.sender_email == "test@example.com"
            assert client.sender_name == "Test Sender"

    def test_brevo_client_missing_api_key(self):
        """Test Brevo client with missing API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = BrevoClient()

            assert client.api_key is None
            assert client.sender_email == "noreply@0admin.com"
            assert client.sender_name == "0Admin"

    @patch("backend.integrations.brevo_client.httpx.Client")
    def test_send_transactional_dry_run(self, mock_httpx):
        """Test sending transactional email in dry-run mode."""
        client = BrevoClient()

        response = client.send_transactional(
            to="test@example.com",
            subject="Test Subject",
            html="<p>Test Content</p>",
            tenant_id="test-tenant",
            dry_run=True,
        )

        # Verify dry-run response
        assert response.success
        assert response.dry_run
        assert response.message_id is not None
        # Message ID is now deterministic UUID (not "dry-run" prefix)
        assert isinstance(response.message_id, str)
        assert len(response.message_id) > 0

        # Verify no HTTP call was made
        mock_httpx.return_value.post.assert_not_called()

    @patch("backend.integrations.brevo_client.httpx.Client")
    def test_send_transactional_no_api_key(self, mock_httpx):
        """Test sending transactional email without API key."""
        with patch.dict(os.environ, {}, clear=True):
            client = BrevoClient()

            response = client.send_transactional(
                to="test@example.com",
                subject="Test Subject",
                html="<p>Test Content</p>",
                tenant_id="test-tenant",
                dry_run=False,
            )

            # Should fall back to dry-run
            assert response.success
            assert response.dry_run
            assert response.message_id is not None

    @patch("backend.integrations.brevo_client.httpx.Client")
    def test_send_transactional_success(self, mock_httpx):
        """Test successful email sending."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "test-message-id"}
        mock_httpx.return_value.post.return_value = mock_response

        with patch.dict(os.environ, {"BREVO_API_KEY": "test-key"}):
            client = BrevoClient()

            response = client.send_transactional(
                to="test@example.com",
                subject="Test Subject",
                html="<p>Test Content</p>",
                tenant_id="test-tenant",
                dry_run=False,
            )

            # Verify success
            assert response.success
            assert not response.dry_run
            # message_id is now deterministic UUID (not Brevo's ID)
            assert response.message_id is not None
            assert isinstance(response.message_id, str)
            # Brevo's ID is stored separately
            assert response.provider_message_id == "test-message-id"
            assert response.error is None

            # Verify HTTP call was made
            mock_httpx.return_value.post.assert_called_once()
            call_args = mock_httpx.return_value.post.call_args
            assert call_args[1]["json"]["to"][0]["email"] == "test@example.com"
            assert call_args[1]["json"]["subject"] == "Test Subject"
            assert call_args[1]["json"]["htmlContent"] == "<p>Test Content</p>"
            assert call_args[1]["json"]["headers"]["X-Tenant-ID"] == "test-tenant"

    @patch("backend.integrations.brevo_client.httpx.Client")
    def test_send_transactional_api_error(self, mock_httpx):
        """Test API error handling."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_httpx.return_value.post.return_value = mock_response

        with patch.dict(os.environ, {"BREVO_API_KEY": "test-key"}):
            client = BrevoClient()

            response = client.send_transactional(
                to="test@example.com",
                subject="Test Subject",
                html="<p>Test Content</p>",
                tenant_id="test-tenant",
                dry_run=False,
            )

            # Verify error handling
            assert not response.success
            assert not response.dry_run
            assert response.message_id is None
            assert "Bad Request" in response.error

    @patch("backend.integrations.brevo_client.httpx.Client")
    def test_send_transactional_network_error(self, mock_httpx):
        """Test network error handling."""
        # Mock network error
        mock_httpx.return_value.post.side_effect = Exception("Network Error")

        with patch.dict(os.environ, {"BREVO_API_KEY": "test-key"}):
            client = BrevoClient()

            response = client.send_transactional(
                to="test@example.com",
                subject="Test Subject",
                html="<p>Test Content</p>",
                tenant_id="test-tenant",
                dry_run=False,
            )

            # Verify error handling
            assert not response.success
            assert not response.dry_run
            assert response.message_id is None
            assert "Network Error" in response.error

    def test_convenience_function(self):
        """Test convenience function."""
        with patch("backend.integrations.brevo_client.BrevoClient") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.send_transactional.return_value = BrevoResponse(
                success=True, message_id="test-id", dry_run=True
            )

            response = send_transactional(
                to="test@example.com",
                subject="Test Subject",
                html="<p>Test Content</p>",
                tenant_id="test-tenant",
                dry_run=True,
            )

            # Verify convenience function works
            assert response.success
            assert response.dry_run
            assert response.message_id == "test-id"

            # Verify client was used correctly
            mock_client.send_transactional.assert_called_once_with(
                "test@example.com", "Test Subject", "<p>Test Content</p>", "test-tenant", True, None
            )

    def test_context_manager(self):
        """Test context manager functionality."""
        with patch("backend.integrations.brevo_client.httpx.Client") as mock_httpx:
            client = BrevoClient()

            with client as c:
                assert c is client

            # Verify client was closed
            mock_httpx.return_value.close.assert_called_once()

    def test_headers_inclusion(self):
        """Test that proper headers are included in requests."""
        with patch.dict(os.environ, {"BREVO_API_KEY": "test-key"}):
            client = BrevoClient()

            # Verify headers are set correctly
            assert client._client.headers["api-key"] == "test-key"
            assert client._client.headers["Content-Type"] == "application/json"
            assert client._client.headers["Accept"] == "application/json"
