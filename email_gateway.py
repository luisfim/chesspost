from dataclasses import dataclass
from pathlib import Path
import re

from database import DATABASE_PATH, get_game
from email_service import (
    DEFAULT_ATTACHMENT_DIRECTORY,
    process_game_email,
)
from invitation_decision_service import process_invitation_reply
from invitation_service import (
    GAME_EMAIL_DOMAIN,
    process_new_game_email,
)


MAIN_EMAIL_ADDRESS = f"play@{GAME_EMAIL_DOMAIN}"

GAME_ADDRESS_PATTERN = re.compile(
    rf"^game-([a-f0-9]{{16}})@{re.escape(GAME_EMAIL_DOMAIN)}$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class OutgoingEmail:
    recipient: str
    subject: str
    body: str
    reply_address: str | None
    attachment_path: Path | None
    delay_hours: int
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class GatewayResult:
    route: str
    processed: bool
    game_code: str | None
    emails: tuple[OutgoingEmail, ...]


def create_gateway_error(
    sender_email: str,
    message: str,
) -> GatewayResult:
    """Create an error response for an unknown recipient address."""
    email = OutgoingEmail(
        recipient=sender_email.strip().lower(),
        subject="[Chesspost] Email could not be processed",
        body=message,
        reply_address=None,
        attachment_path=None,
        delay_hours=0,
    )

    return GatewayResult(
        route="unknown",
        processed=False,
        game_code=None,
        emails=(email,),
    )


def extract_game_code(recipient_email: str) -> str | None:
    """Extract a game code from a Chesspost game address."""
    match = GAME_ADDRESS_PATTERN.fullmatch(
        recipient_email.strip().lower()
    )

    if match is None:
        return None

    return match.group(1).lower()


def process_incoming_email(
    *,
    sender_email: str,
    recipient_email: str,
    subject: str,
    body: str,
    db_path: Path = DATABASE_PATH,
    attachment_directory: Path = DEFAULT_ATTACHMENT_DIRECTORY,
) -> GatewayResult:
    """Route an incoming email to the correct Chesspost service."""
    sender_email = sender_email.strip().lower()
    recipient_email = recipient_email.strip().lower()

    if recipient_email == MAIN_EMAIL_ADDRESS:
        invitation = process_new_game_email(
            sender_email=sender_email,
            subject=subject,
            body=body,
            db_path=db_path,
        )

        outgoing_email = OutgoingEmail(
            recipient=invitation.recipient,
            subject=invitation.subject,
            body=invitation.body,
            reply_address=invitation.reply_address,
            attachment_path=None,
            delay_hours=0,
        )

        game_code = (
            invitation.game.code
            if invitation.game is not None
            else None
        )

        return GatewayResult(
            route="new_game",
            processed=invitation.request_accepted,
            game_code=game_code,
            emails=(outgoing_email,),
        )

    game_code = extract_game_code(recipient_email)

    if game_code is None:
        return create_gateway_error(
            sender_email,
            (
                "This is not a recognized Chesspost email address.\n\n"
                f"To start a new game, email {MAIN_EMAIL_ADDRESS} "
                "and put your opponent's email address in the subject."
            ),
        )

    game = get_game(game_code, db_path)

    if game is not None and game.status == "invited":
        decision = process_invitation_reply(
            game_code=game_code,
            sender_email=sender_email,
            email_body=body,
            db_path=db_path,
        )

        outgoing_emails = tuple(
            OutgoingEmail(
                recipient=email.recipient,
                subject=email.subject,
                body=email.body,
                reply_address=email.reply_address,
                attachment_path=None,
                delay_hours=0,
            )
            for email in decision.emails
        )

        return GatewayResult(
            route="invitation_reply",
            processed=decision.processed,
            game_code=game_code,
            emails=outgoing_emails,
        )

    move_response = process_game_email(
        game_code=game_code,
        sender_email=sender_email,
        email_body=body,
        db_path=db_path,
        attachment_directory=attachment_directory,
    )

    outgoing_email = OutgoingEmail(
        recipient=move_response.recipient,
        subject=move_response.subject,
        body=move_response.body,
        reply_address=recipient_email,
        attachment_path=move_response.attachment_path,
        delay_hours=move_response.delay_hours or 0,
    )

    return GatewayResult(
        route="game_message",
        processed=move_response.delivered_to_opponent,
        game_code=game_code,
        emails=(outgoing_email,),
    )
