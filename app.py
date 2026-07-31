import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from email_gateway import process_incoming_email


app = FastAPI(
    title="Chesspost",
    description="Play correspondence chess entirely through email.",
    version="0.1.0",
)


class IncomingEmailWebhook(BaseModel):
    """Temporary provider-independent inbound email format."""

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
    """Process a simulated inbound email webhook."""
    result = process_incoming_email(
        sender_email=email.sender_email,
        recipient_email=email.recipient_email,
        subject=email.subject,
        body=email.body,
        db_path=database_path(),
        attachment_directory=attachment_directory(),
    )

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
    }
