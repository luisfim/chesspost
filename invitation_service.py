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


def process_rematch_request(
    previous_game: Game,
    sender_email: str,
    db_path: Path = DATABASE_PATH,
) -> InvitationResponse:
    """Create a rematch with reversed colors."""
    sender_email = sender_email.strip().lower()

    if sender_email not in {
        previous_game.white_email,
        previous_game.black_email,
    }:
        return InvitationResponse(
            request_accepted=False,
            recipient=sender_email,
            subject="[Chesspost] Rematch could not be created",
            body="This email address is not a player in this game.",
            reply_address=None,
            game=None,
        )

    if previous_game.status != "finished":
        return InvitationResponse(
            request_accepted=False,
            recipient=sender_email,
            subject="[Chesspost] Rematch could not be created",
            body=(
                "A rematch can only be requested after "
                "the current game has finished."
            ),
            reply_address=None,
            game=None,
        )

    if sender_email == previous_game.white_email:
        opponent_email = previous_game.black_email
        requested_color = "black"
    else:
        opponent_email = previous_game.white_email
        requested_color = "white"

    game = create_invited_game(
        inviter_email=sender_email,
        opponent_email=opponent_email,
        requested_color=requested_color,
        delivery_delay_hours=(
            previous_game.delivery_delay_hours
        ),
        db_path=db_path,
    )

    opponent_color = get_player_color(
        game,
        opponent_email,
    )

    reply_address = game_email_address(game.code)
    short_code = game.code[:8].upper()

    if game.delivery_delay_hours == 0:
        delay_description = (
            "Moves will be delivered immediately."
        )
    else:
        delay_description = (
            f"Moves will be delivered after "
            f"{game.delivery_delay_hours} hours."
        )

    return InvitationResponse(
        request_accepted=True,
        recipient=opponent_email,
        subject=(
            f"[Chesspost {short_code}] "
            f"Rematch invitation from {sender_email}"
        ),
        body=(
            f"{sender_email} requested a rematch.\n\n"
            "Colors have been reversed from the previous game.\n"
            f"You will play {opponent_color}.\n"
            f"{delay_description}\n\n"
            "Reply with:\n\n"
            "accept\n\n"
            "or:\n\n"
            "decline"
        ),
        reply_address=reply_address,
        game=game,
    )
