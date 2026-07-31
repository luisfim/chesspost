from dataclasses import dataclass
import os
from pathlib import Path

from database import DATABASE_PATH, Game, create_invited_game
from new_game_parser import parse_new_game_email


GAME_EMAIL_DOMAIN = os.getenv(
    "CHESSPOST_EMAIL_DOMAIN",
    "chesspost.test",
).strip().lower()


@dataclass(frozen=True)
class InvitationResponse:
    request_accepted: bool
    recipient: str
    subject: str
    body: str
    reply_address: str | None
    game: Game | None


def get_player_color(game: Game, email: str) -> str:
    """Return the player's assigned color."""
    email = email.strip().lower()

    if email == game.white_email:
        return "White"

    if email == game.black_email:
        return "Black"

    raise ValueError("This email address is not part of the game.")


def game_email_address(game_code: str) -> str:
    """Return the temporary email address used for a game."""
    return f"game-{game_code}@{GAME_EMAIL_DOMAIN}"


def process_new_game_email(
    sender_email: str,
    subject: str,
    body: str,
    db_path: Path = DATABASE_PATH,
) -> InvitationResponse:
    """Create a pending game from an email sent to Chesspost."""
    request = parse_new_game_email(
        sender_email=sender_email,
        subject=subject,
        body=body,
    )

    if not request.valid or request.opponent_email is None:
        return InvitationResponse(
            request_accepted=False,
            recipient=request.sender_email,
            subject="[Chesspost] Game could not be created",
            body=(
                f"{request.message}\n\n"
                "To start a game, put your opponent's email address "
                "in the subject."
            ),
            reply_address=None,
            game=None,
        )

    game = create_invited_game(
        inviter_email=request.sender_email,
        opponent_email=request.opponent_email,
        requested_color=request.color,
        delivery_delay_hours=request.delay_hours,
        db_path=db_path,
    )

    opponent_color = get_player_color(
        game,
        request.opponent_email,
    )
    reply_address = game_email_address(game.code)
    short_code = game.code[:8].upper()

    if game.delivery_delay_hours == 0:
        delay_description = "Moves will be delivered immediately."
    else:
        delay_description = (
            f"Moves will be delivered after "
            f"{game.delivery_delay_hours} hours."
        )

    return InvitationResponse(
        request_accepted=True,
        recipient=request.opponent_email,
        subject=(
            f"[Chesspost {short_code}] "
            f"Chess invitation from {request.sender_email}"
        ),
        body=(
            f"{request.sender_email} invited you to play "
            "correspondence chess.\n\n"
            f"You will play {opponent_color}.\n"
            f"{delay_description}\n\n"
            "Reply to this email with:\n\n"
            "accept\n\n"
            "To reject the invitation, reply with:\n\n"
            "decline"
        ),
        reply_address=reply_address,
        game=game,
    )
