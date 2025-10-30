"""Brevo webhook receiver with multiple authentication modes (HMAC, Token, Basic Auth)."""

import base64
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.comm.brevo_schema import parse_brevo_event
from agents.comm.event_sink import EventSink
from agents.comm.events import BrevoEventMapper

app = FastAPI(title="Brevo Webhook Receiver")

# Get webhook configuration from environment
AUTH_MODE = os.getenv("BREVO_WEBHOOK_AUTH_MODE", "token").lower()  # token|basic|hmac
WEBHOOK_TOKEN = os.getenv("BREVO_WEBHOOK_TOKEN")
WEBHOOK_SECRET = os.getenv("BREVO_WEBHOOK_SECRET")  # For HMAC
WEBHOOK_BASIC_USER = os.getenv("BREVO_WEBHOOK_BASIC_USER")
WEBHOOK_BASIC_PASS = os.getenv("BREVO_WEBHOOK_BASIC_PASS")
TENANT_DEFAULT = os.getenv("TENANT_DEFAULT", "00000000-0000-0000-0000-000000000001")

# Initialize event sink
event_sink = EventSink()


class WebhookResponse(BaseModel):
    """Webhook response model."""

    status: str
    event_id: str | None = None
    tenant_id: str | None = None


def verify_token_auth(
    authorization: str | None, x_webhook_token: str | None, expected_token: str | None
) -> bool:
    """Verify token authentication (Bearer or X-Webhook-Token header).

    Args:
        authorization: Authorization header value
        x_webhook_token: X-Webhook-Token header value
        expected_token: Expected token value

    Returns:
        True if token is valid
    """
    if not expected_token:
        return False

    # Check Authorization: Bearer <token>
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_token = parts[1].strip()
            return hmac.compare_digest(provided_token, expected_token)

    # Check X-Webhook-Token header
    if x_webhook_token:
        return hmac.compare_digest(x_webhook_token.strip(), expected_token)

    return False


def verify_basic_auth(authorization: str | None, expected_user: str | None, expected_pass: str | None) -> bool:
    """Verify Basic Auth authentication.

    Args:
        authorization: Authorization header value
        expected_user: Expected username
        expected_pass: Expected password

    Returns:
        True if credentials are valid
    """
    if not expected_user or not expected_pass:
        return False

    if not authorization:
        return False

    # Parse Basic auth header
    if not authorization.lower().startswith("basic "):
        return False

    try:
        encoded = authorization[6:].strip()  # Remove "Basic " prefix
        decoded = base64.b64decode(encoded).decode("utf-8")
        user, password = decoded.split(":", 1)

        # Constant-time comparison
        return hmac.compare_digest(user, expected_user) and hmac.compare_digest(
            password, expected_pass
        )
    except Exception:
        return False


def verify_hmac_signature(body: bytes, signature_header: str | None, secret: str | None) -> bool:
    """Verify HMAC signature for Brevo webhook.

    Args:
        body: Raw request body
        signature_header: X-Brevo-Signature header value (format: sha256=<hex>)
        secret: Webhook secret

    Returns:
        True if signature is valid
    """
    if not secret or not signature_header:
        return False

    # Parse signature header (format: sha256=<hexdigest>)
    if not signature_header.startswith("sha256="):
        return False

    signature_hex = signature_header[7:]  # Remove "sha256=" prefix

    try:
        # Compute HMAC-SHA256
        computed_signature = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(computed_signature, signature_hex)
    except Exception:
        return False


def verify_authentication(
    auth_mode: str,
    request: Request,
    authorization: str | None,
    x_webhook_token: str | None,
    x_brevo_signature: str | None,
    body: bytes,
) -> bool:
    """Verify authentication based on configured mode.

    Args:
        auth_mode: Authentication mode (token|basic|hmac)
        request: FastAPI request object
        authorization: Authorization header
        x_webhook_token: X-Webhook-Token header
        x_brevo_signature: X-Brevo-Signature header
        body: Raw request body

    Returns:
        True if authentication is valid
    """
    if auth_mode == "token":
        return verify_token_auth(authorization, x_webhook_token, WEBHOOK_TOKEN)
    elif auth_mode == "basic":
        return verify_basic_auth(authorization, WEBHOOK_BASIC_USER, WEBHOOK_BASIC_PASS)
    elif auth_mode == "hmac":
        return verify_hmac_signature(body, x_brevo_signature, WEBHOOK_SECRET)
    else:
        return False


@app.post("/operate/brevo/webhook")
async def brevo_webhook(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    x_webhook_token: str | None = Header(None, alias="X-Webhook-Token"),
    x_brevo_signature: str | None = Header(None, alias="X-Brevo-Signature"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> JSONResponse:
    """Receive Brevo webhook events with configurable authentication (token/basic/hmac).

    Args:
        request: FastAPI request object
        authorization: Authorization header (Bearer token or Basic auth)
        x_webhook_token: X-Webhook-Token header (alternative to Authorization Bearer)
        x_brevo_signature: X-Brevo-Signature header (for HMAC mode)
        x_tenant_id: X-Tenant-ID header (optional)

    Returns:
        JSON response with status and event ID
    """
    # Read raw body (needed for HMAC verification)
    body = await request.body()

    # Verify authentication based on configured mode
    if not verify_authentication(
        AUTH_MODE, request, authorization, x_webhook_token, x_brevo_signature, body
    ):
        error_msg = {
            "token": "Invalid or missing token",
            "basic": "Invalid or missing credentials",
            "hmac": "Invalid signature",
        }.get(AUTH_MODE, "Authentication failed")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "error", "error": error_msg},
        )

    # Parse JSON payload
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "error": f"Invalid JSON: {str(e)}"},
        )

    # Extract tenant ID
    tenant_id = BrevoEventMapper.extract_tenant_id(payload, x_tenant_id)
    if not tenant_id:
        tenant_id = TENANT_DEFAULT

    # Parse Brevo event
    try:
        brevo_event = parse_brevo_event(payload)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "error": f"Invalid event payload: {str(e)}"},
        )

    # Map to normalized event
    try:
        # Extract provider event ID if available
        provider_event_id = payload.get("id") or payload.get("event-id")
        comm_event = BrevoEventMapper.map_to_comm_event(
            brevo_event, tenant_id, provider_event_id=provider_event_id
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "error": f"Event mapping failed: {str(e)}"},
        )

    # Persist event
    try:
        was_persisted, event_file = event_sink.persist(comm_event)
        if not was_persisted:
            # Event was duplicate (idempotency)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "ok",
                    "event_id": None,
                    "tenant_id": tenant_id,
                    "duplicate": True,
                },
            )

        # Extract event ID from file name
        event_id = event_file.stem.replace("event-", "") if event_file else str(uuid4())
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ok",
                "event_id": event_id,
                "tenant_id": tenant_id,
                "event_type": comm_event.event_type,
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "error": f"Persistence failed: {str(e)}"},
        )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(content={"status": "ok"})

