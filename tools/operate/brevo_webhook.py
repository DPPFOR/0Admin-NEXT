"""Brevo webhook receiver with HMAC verification."""

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

# Get webhook secret from environment
WEBHOOK_SECRET = os.getenv("BREVO_WEBHOOK_SECRET")
TENANT_DEFAULT = os.getenv("TENANT_DEFAULT", "00000000-0000-0000-0000-000000000001")

# Initialize event sink
event_sink = EventSink()


class WebhookResponse(BaseModel):
    """Webhook response model."""

    status: str
    event_id: str | None = None
    tenant_id: str | None = None


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


@app.post("/operate/brevo/webhook")
async def brevo_webhook(
    request: Request,
    x_brevo_signature: str | None = Header(None, alias="X-Brevo-Signature"),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> JSONResponse:
    """Receive Brevo webhook events with HMAC verification.

    Args:
        request: FastAPI request object
        x_brevo_signature: X-Brevo-Signature header
        x_tenant_id: X-Tenant-ID header (optional)

    Returns:
        JSON response with status and event ID
    """
    # Read raw body for HMAC verification
    body = await request.body()

    # Verify HMAC signature
    if not verify_hmac_signature(body, x_brevo_signature, WEBHOOK_SECRET):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"status": "error", "error": "Invalid signature"},
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

