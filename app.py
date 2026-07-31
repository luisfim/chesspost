import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from email_gateway import GatewayResult, process_incoming_email
from outbound_mailer import (
    DeliveryResult,
    dispatch_outgoing_emails,
)
from resend_inbound import (
    fetch_received_email,
    get_received_email_id,
    verify_resend_event,
)


app = FastAPI(
    title="Chesspost",
    description="Play correspondence chess entirely through email.",
    version="0.2.0",
)


class IncomingEmailWebhook(BaseModel):
    """Provider-independent test email format."""

    sender_email: str = Field(min_length=1)
    recipient_email: str = Field(min_length=1)
    subject: str = ""
    body: str = ""


def database_path() -> Path:
    """Return the configured SQLite database path."""
    return Path(
        os.getenv(
            "CHESSPOST_DATABASE",
            "chesspost.db",
        )
    )


def attachment_directory() -> Path:
    """Return the configured board-image directory."""
    return Path(
        os.getenv(
            "CHESSPOST_ATTACHMENTS",
            "output/boards",
        )
    )


def serialize_result(
    result: GatewayResult,
    deliveries: tuple[DeliveryResult, ...],
) -> dict[str, object]:
    """Convert gateway and delivery results into JSON."""
    return {
        "route": result.route,
        "processed": result.processed,
        "game_code": result.game_code,
        "emails": [
            {
                "recipient": outgoing.recipient,
                "subject": outgoing.subject,
                "body": outgoing.body,
                "reply_address": outgoing.reply_address,
                "attachment_path": (
                    str(outgoing.attachment_path)
                    if outgoing.attachment_path is not None
                    else None
                ),
                "delay_hours": outgoing.delay_hours,
            }
            for outgoing in result.emails
        ],
        "deliveries": [
            {
                "recipient": delivery.recipient,
                "mode": delivery.mode,
                "provider_id": delivery.provider_id,
                "scheduled": delivery.scheduled,
            }
            for delivery in deliveries
        ],
    }


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Chesspost",
        "message": "Play correspondence chess through email.",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/inbound-email")
def inbound_email(
    email: IncomingEmailWebhook,
) -> dict[str, object]:
    """Process a simulated inbound email."""
    result = process_incoming_email(
        sender_email=email.sender_email,
        recipient_email=email.recipient_email,
        subject=email.subject,
        body=email.body,
        db_path=database_path(),
        attachment_directory=attachment_directory(),
    )

    deliveries = dispatch_outgoing_emails(result.emails)

    return serialize_result(result, deliveries)


@app.post("/webhooks/resend")
async def resend_webhook(
    request: Request,
) -> dict[str, object]:
    """Process a verified Resend inbound-email event."""
    webhook_secret = os.getenv("RESEND_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="RESEND_WEBHOOK_SECRET is not configured.",
        )

    raw_payload = await request.body()

    try:
        event = verify_resend_event(
            raw_payload=raw_payload,
            headers=request.headers,
            webhook_secret=webhook_secret,
        )
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid Resend webhook signature.",
        ) from error

    try:
        email_id = get_received_email_id(event)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    if email_id is None:
        return {
            "ignored": True,
            "event_type": event.get("type"),
        }

    try:
        received_email = fetch_received_email(email_id)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    result = process_incoming_email(
        sender_email=received_email.sender_email,
        recipient_email=received_email.recipient_email,
        subject=received_email.subject,
        body=received_email.body,
        db_path=database_path(),
        attachment_directory=attachment_directory(),
    )

    deliveries = dispatch_outgoing_emails(result.emails)

    response = serialize_result(result, deliveries)
    response["received_email_id"] = received_email.email_id

    return response
