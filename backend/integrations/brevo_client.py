"""Brevo (Sendinblue) transactional email client for MVR notifications.

This module provides a client for sending transactional emails via Brevo API.
Supports dry-run mode for testing and development.
"""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from agents.comm.outbound_tags import generate_message_id


@dataclass
class BrevoEmail:
    """Email data structure for Brevo API."""

    to: str
    subject: str
    html: str
    tenant_id: str
    dry_run: bool = False


@dataclass
class BrevoResponse:
    """Response from Brevo API."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    dry_run: bool = False


class BrevoClient:
    """Brevo API client for transactional emails."""

    def __init__(self):
        """Initialize Brevo client with environment configuration."""
        self.logger = logging.getLogger(__name__)

        # Load configuration from environment
        self.api_key = os.getenv("BREVO_API_KEY")
        self.sender_email = os.getenv("BREVO_SENDER_EMAIL", "noreply@0admin.com")
        self.sender_name = os.getenv("BREVO_SENDER_NAME", "0Admin")
        self.base_url = "https://api.brevo.com/v3"

        # Hard-bounce tracking (in production, this would be in Redis/DB)
        self._hard_bounces = set()

        # Soft-bounce tracking: email -> [(timestamp, attempt_count)]
        # Policy: Max 3 Versuche in 72h, danach Hard-Bounce
        self._soft_bounces: dict[str, list[datetime]] = {}

        # Validate required configuration
        if not self.api_key:
            self.logger.warning("BREVO_API_KEY not set - only dry-run mode available")

        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "api-key": self.api_key or "dry-run",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def send_transactional(
        self,
        to: str,
        subject: str,
        html: str,
        tenant_id: str,
        dry_run: bool = False,
        invoice_no: str | None = None,
    ) -> BrevoResponse:
        """Send transactional email via Brevo API.

        Args:
            to: Recipient email address
            subject: Email subject
            html: HTML content
            tenant_id: Tenant identifier for tracking
            dry_run: If True, simulate sending without actual API call
            invoice_no: Optional invoice number for deterministic message ID

        Returns:
            BrevoResponse with success status and details
        """
        # Check hard-bounce list first (only if email is provided)
        if to and self.is_hard_bounced(to):
            self.logger.warning(
                "Skipping email to hard-bounced address", extra={"tenant_id": tenant_id, "to": to}
            )
            return BrevoResponse(
                success=False, error="Email address is on hard-bounce list", dry_run=False
            )

        # Check soft-bounce policy: max 3 attempts in 72h
        if to and not dry_run:
            can_retry, reason = self._check_soft_bounce_policy(to)
            if not can_retry:
                self.logger.warning(
                    "Soft-bounce policy exceeded - moving to hard-bounce",
                    extra={"tenant_id": tenant_id, "to": to, "reason": reason},
                )
                self.add_hard_bounce(to)
                return BrevoResponse(
                    success=False, error=f"Soft-bounce policy exceeded: {reason}", dry_run=False
                )

        if dry_run or not self.api_key:
            return self._handle_dry_run(to, subject, tenant_id)

        try:
            # Generate deterministic message ID
            message_id = generate_message_id(
                tenant_id=tenant_id, invoice_no=invoice_no, ts=datetime.now(UTC)
            )

            # Prepare email data
            email_data = {
                "sender": {"name": self.sender_name, "email": self.sender_email},
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": html,
                "headers": {
                    "X-Tenant-ID": tenant_id,
                    "X-Message-ID": message_id,
                    "X-MVR-Notification": "true",
                },
            }

            # Send via Brevo API
            response = self._client.post("/smtp/email", json=email_data)

            if response.status_code == 201:
                result = response.json()
                message_id = result.get("messageId")

                self.logger.info(
                    "Email sent successfully via Brevo",
                    extra={
                        "tenant_id": tenant_id,
                        "to": to,
                        "message_id": message_id,
                        "subject": subject[:50] + "..." if len(subject) > 50 else subject,
                    },
                )

                return BrevoResponse(success=True, message_id=message_id, dry_run=False)
            else:
                error_msg = f"Brevo API error: {response.status_code} - {response.text}"

                # Check if this is a hard bounce (400 with invalid email)
                if response.status_code == 400 and "invalid" in response.text.lower():
                    self.logger.error(
                        "Hard bounce detected - adding to blocklist",
                        extra={
                            "tenant_id": tenant_id,
                            "to": to,
                            "status_code": response.status_code,
                        },
                    )
                    self.add_hard_bounce(to)

                self.logger.error(
                    f"Failed to send email via Brevo: {error_msg}",
                    extra={"tenant_id": tenant_id, "to": to, "status_code": response.status_code},
                )

                return BrevoResponse(success=False, error=error_msg, dry_run=False)

        except httpx.RequestError as e:
            error_msg = f"Network error sending email: {str(e)}"
            self.logger.error(
                f"Network error sending email: {error_msg}",
                extra={"tenant_id": tenant_id, "to": to, "error": str(e)},
            )

            return BrevoResponse(success=False, error=error_msg, dry_run=False)

        except Exception as e:
            error_msg = f"Unexpected error sending email: {str(e)}"
            self.logger.error(
                f"Unexpected error sending email: {error_msg}",
                extra={"tenant_id": tenant_id, "to": to, "error": str(e)},
            )

            return BrevoResponse(success=False, error=error_msg, dry_run=False)

    def _handle_dry_run(self, to: str, subject: str, tenant_id: str) -> BrevoResponse:
        """Handle dry-run mode - simulate email sending without API call.

        Args:
            to: Recipient email address
            subject: Email subject
            tenant_id: Tenant identifier

        Returns:
            BrevoResponse indicating dry-run success
        """
        self.logger.info(
            "DRY-RUN: Would send email via Brevo",
            extra={
                "tenant_id": tenant_id,
                "to": to,
                "subject": subject[:50] + "..." if len(subject) > 50 else subject,
                "dry_run": True,
            },
        )

        message_id = generate_message_id(
            tenant_id=tenant_id, invoice_no=None, ts=datetime.now(UTC)
        )
        return BrevoResponse(success=True, message_id=message_id, dry_run=True)

    def close(self):
        """Close HTTP client connection."""
        if hasattr(self, "_client"):
            self._client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def is_hard_bounced(self, email: str) -> bool:
        """Check if email is on hard-bounce list.

        Args:
            email: Email address to check

        Returns:
            True if email is hard-bounced
        """
        return email.lower() in self._hard_bounces

    def add_hard_bounce(self, email: str) -> None:
        """Add email to hard-bounce list.

        Args:
            email: Email address to add
        """
        self._hard_bounces.add(email.lower())
        self.logger.info(f"Added email to hard-bounce list: {email}")

    def remove_hard_bounce(self, email: str) -> None:
        """Remove email from hard-bounce list.

        Args:
            email: Email address to remove
        """
        self._hard_bounces.discard(email.lower())
        self.logger.info(f"Removed email from hard-bounce list: {email}")

    def get_hard_bounces(self) -> set:
        """Get all hard-bounced email addresses.

        Returns:
            Set of hard-bounced email addresses
        """
        return self._hard_bounces.copy()

    def _check_soft_bounce_policy(self, email: str) -> tuple[bool, str | None]:
        """Check soft-bounce policy: max 3 attempts in 72h.

        Args:
            email: Email address to check

        Returns:
            Tuple (can_retry, reason)
        """
        email_lower = email.lower()
        now = datetime.now(UTC)
        window_start = now - timedelta(hours=72)

        if email_lower not in self._soft_bounces:
            return True, None

        # Clean old attempts (outside 72h window)
        attempts = self._soft_bounces[email_lower]
        attempts_in_window = [ts for ts in attempts if ts > window_start]
        self._soft_bounces[email_lower] = attempts_in_window

        # Check policy: max 3 attempts in 72h
        if len(attempts_in_window) >= 3:
            return (
                False,
                f"Max 3 soft-bounce attempts in 72h exceeded ({len(attempts_in_window)} attempts)",
            )

        return True, None

    def record_soft_bounce(self, email: str) -> None:
        """Record a soft-bounce attempt.

        Args:
            email: Email address that soft-bounced
        """
        email_lower = email.lower()
        now = datetime.now(UTC)

        if email_lower not in self._soft_bounces:
            self._soft_bounces[email_lower] = []

        self._soft_bounces[email_lower].append(now)

        # Check if policy exceeded
        can_retry, reason = self._check_soft_bounce_policy(email)
        if not can_retry:
            self.logger.warning(
                "Soft-bounce policy exceeded - promoting to hard-bounce",
                extra={"email": email, "reason": reason},
            )
            self.add_hard_bounce(email)
        else:
            attempt_count = len(self._soft_bounces[email_lower])
            self.logger.info(
                "Soft-bounce recorded", extra={"email": email, "attempt": attempt_count, "max": 3}
            )

    def get_soft_bounce_status(self, email: str) -> dict[str, Any]:
        """Get soft-bounce status for email.

        Args:
            email: Email address to check

        Returns:
            Dictionary with soft-bounce status
        """
        email_lower = email.lower()

        if email_lower not in self._soft_bounces:
            return {
                "email": email,
                "attempts": 0,
                "last_attempt": None,
                "can_retry": True,
                "policy": "max 3 attempts in 72h",
            }

        now = datetime.now(UTC)
        window_start = now - timedelta(hours=72)
        attempts_in_window = [ts for ts in self._soft_bounces[email_lower] if ts > window_start]
        can_retry, reason = self._check_soft_bounce_policy(email)

        return {
            "email": email,
            "attempts": len(attempts_in_window),
            "last_attempt": max(attempts_in_window).isoformat() if attempts_in_window else None,
            "can_retry": can_retry,
            "reason": reason,
            "policy": "max 3 attempts in 72h",
        }


# Convenience function for direct usage
def send_transactional(
    to: str,
    subject: str,
    html: str,
    tenant_id: str,
    dry_run: bool = False,
    invoice_no: str | None = None,
) -> BrevoResponse:
    """Convenience function to send transactional email.

    Args:
        to: Recipient email address
        subject: Email subject
        html: HTML content
        tenant_id: Tenant identifier
        dry_run: If True, simulate sending without actual API call
        invoice_no: Optional invoice number for deterministic message ID

    Returns:
        BrevoResponse with success status and details
    """
    with BrevoClient() as client:
        return client.send_transactional(to, subject, html, tenant_id, dry_run, invoice_no)
