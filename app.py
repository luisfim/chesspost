from dataclasses import replace
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from database import get_game
from email_gateway import GatewayResult, process_incoming_email
from outbound_mailer import (
    DeliveryResult,
    dispatch_outgoing_emails,
)
from inbound_event_store import (
    claim_inbound_email,
    mark_inbound_email_processed,
    release_inbound_email_claim,
)
from resend_inbound import (
    ReceivedEmail,
    fetch_received_email,
    get_received_email_id,
    verify_resend_event,
)
from thread_store import (
    build_reply_headers,
    build_reply_subject,
    save_thread_context,
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


def save_received_thread_context(
    result: GatewayResult,
    received_email: ReceivedEmail,
) -> None:
    """Save thread information when the sender belongs to the game."""
    if result.route == "rematch":
        return

    if result.game_code is None or not received_email.message_id:
        return

    game = get_game(
        result.game_code,
        database_path(),
    )

    if game is None:
        return

    sender_email = received_email.sender_email.strip().lower()

    if sender_email not in {
        game.white_email,
        game.black_email,
    }:
        return

    save_thread_context(
        game_code=game.code,
        player_email=sender_email,
        message_id=received_email.message_id,
        references=received_email.references,
        subject=received_email.subject,
        db_path=database_path(),
    )


def apply_thread_headers(
    result: GatewayResult,
) -> GatewayResult:
    """Attach each recipient's saved email-thread headers."""
    if result.game_code is None:
        return result

    threaded_emails = []

    for outgoing in result.emails:
        headers = build_reply_headers(
            game_code=result.game_code,
            player_email=outgoing.recipient,
            db_path=database_path(),
        )

        reply_subject = build_reply_subject(
            game_code=result.game_code,
            player_email=outgoing.recipient,
            db_path=database_path(),
        )

        subject = reply_subject or outgoing.subject

        if (
            headers
            and reply_subject is None
            and not subject.lower().startswith("re:")
        ):
            subject = f"Re: {subject}"

        threaded_emails.append(
            replace(
                outgoing,
                subject=subject,
                headers=headers or None,
            )
        )

    return replace(
        result,
        emails=tuple(threaded_emails),
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
                "headers": outgoing.headers,
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

    result = apply_thread_headers(result)

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

    event_id = request.headers.get("svix-id", "").strip() or None

    claimed = claim_inbound_email(
        email_id=email_id,
        event_id=event_id,
        db_path=database_path(),
    )

    if not claimed:
        return {
            "duplicate": True,
            "received_email_id": email_id,
        }

    try:
        event_data = event.get("data")
        event_message_id = ""

        if isinstance(event_data, dict):
            event_message_id = str(
                event_data.get("message_id", "")
            ).strip()

        received_email = fetch_received_email(
            email_id,
            fallback_message_id=event_message_id,
        )

        result = process_incoming_email(
            sender_email=received_email.sender_email,
            recipient_email=received_email.recipient_email,
            subject=received_email.subject,
            body=received_email.body,
            db_path=database_path(),
            attachment_directory=attachment_directory(),
        )

        save_received_thread_context(
            result,
            received_email,
        )

        result = apply_thread_headers(result)

        deliveries = dispatch_outgoing_emails(
            result.emails
        )

        mark_inbound_email_processed(
            email_id,
            database_path(),
        )

        response = serialize_result(
            result,
            deliveries,
        )
        response["received_email_id"] = (
            received_email.email_id
        )

        return response

    except HTTPException:
        release_inbound_email_claim(
            email_id,
            database_path(),
        )
        raise

    except Exception:
        release_inbound_email_claim(
            email_id,
            database_path(),
        )
        raise

