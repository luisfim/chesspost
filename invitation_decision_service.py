from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from database import DATABASE_PATH, Game, connect, get_game
from email_parser import parse_email_body
from invitation_service import game_email_address


@dataclass(frozen=True)
class PreparedEmail:
    recipient: str
    subject: str
    body: str
    reply_address: str | None


@dataclass(frozen=True)
class InvitationDecisionResult:
    processed: bool
    decision: str | None
    game: Game | None
    emails: tuple[PreparedEmail, ...]


def get_invited_opponent(game: Game) -> str:
    """Return the person who was invited to the game."""
    inviter = game.invited_by_email

    if inviter is None:
        raise ValueError("This game does not contain invitation information.")

    if inviter == game.white_email:
        return game.black_email

    if inviter == game.black_email:
        return game.white_email

    raise ValueError("The inviter is not one of the game's players.")


def create_error_result(
    sender_email: str,
    game_code: str,
    message: str,
    game: Game | None = None,
) -> InvitationDecisionResult:
    """Prepare an error email for an invalid invitation response."""
    short_code = game_code[:8].upper()

    email = PreparedEmail(
        recipient=sender_email,
        subject=f"[Chesspost {short_code}] Invitation response not accepted",
        body=message,
        reply_address=(
            game_email_address(game_code)
            if game is not None
            else None
        ),
    )

    return InvitationDecisionResult(
        processed=False,
        decision=None,
        game=game,
        emails=(email,),
    )


def process_invitation_reply(
    game_code: str,
    sender_email: str,
    email_body: str,
    db_path: Path = DATABASE_PATH,
) -> InvitationDecisionResult:
    """Process an accept or decline reply to a game invitation."""
    sender_email = sender_email.strip().lower()
    game = get_game(game_code, db_path)

    if game is None:
        return create_error_result(
            sender_email=sender_email,
            game_code=game_code,
            message="This Chesspost invitation could not be found.",
        )

    if game.status != "invited":
        return create_error_result(
            sender_email=sender_email,
            game_code=game_code,
            message="This invitation is no longer waiting for a response.",
            game=game,
        )

    if sender_email not in {
        game.white_email,
        game.black_email,
    }:
        return create_error_result(
            sender_email=sender_email,
            game_code=game_code,
            message="This email address is not part of this game.",
            game=game,
        )

    invited_opponent = get_invited_opponent(game)

    if sender_email != invited_opponent:
        return create_error_result(
            sender_email=sender_email,
            game_code=game_code,
            message=(
                "Only the invited opponent can accept or decline "
                "this invitation."
            ),
            game=game,
        )

    parsed_email = parse_email_body(email_body)

    if (
        not parsed_email.valid
        or parsed_email.command not in {"accept", "decline"}
    ):
        return create_error_result(
            sender_email=sender_email,
            game_code=game_code,
            message=(
                "Reply with only one of these commands:\n\n"
                "accept\n\n"
                "or\n\n"
                "decline"
            ),
            game=game,
        )

    now = datetime.now(timezone.utc).isoformat()
    reply_address = game_email_address(game.code)
    short_code = game.code[:8].upper()

    if parsed_email.command == "decline":
        with connect(db_path) as connection:
            connection.execute(
                """
                UPDATE games
                SET
                    status = ?,
                    updated_at = ?
                WHERE code = ?
                """,
                (
                    "declined",
                    now,
                    game.code,
                ),
            )

        updated_game = get_game(game.code, db_path)

        if updated_game is None:
            raise RuntimeError("The declined game could not be loaded.")

        inviter_email = game.invited_by_email

        if inviter_email is None:
            raise RuntimeError("The invitation does not have an inviter.")

        inviter_email_message = PreparedEmail(
            recipient=inviter_email,
            subject=f"[Chesspost {short_code}] Invitation declined",
            body=(
                f"{sender_email} declined your chess invitation.\n\n"
                "No game was started."
            ),
            reply_address=None,
        )

        opponent_confirmation = PreparedEmail(
            recipient=sender_email,
            subject=f"[Chesspost {short_code}] Invitation declined",
            body=(
                "You declined the chess invitation.\n\n"
                "No game was started."
            ),
            reply_address=None,
        )

        return InvitationDecisionResult(
            processed=True,
            decision="decline",
            game=updated_game,
            emails=(
                inviter_email_message,
                opponent_confirmation,
            ),
        )

    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE games
            SET
                status = ?,
                accepted_at = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (
                "active",
                now,
                now,
                game.code,
            ),
        )

    updated_game = get_game(game.code, db_path)

    if updated_game is None:
        raise RuntimeError("The accepted game could not be loaded.")

    if updated_game.delivery_delay_hours == 0:
        delay_description = "Moves will be delivered immediately."
    else:
        delay_description = (
            f"Moves will be delivered after "
            f"{updated_game.delivery_delay_hours} hours."
        )

    white_email = PreparedEmail(
        recipient=updated_game.white_email,
        subject=f"[Chesspost {short_code}] Game started — White to move",
        body=(
            "The chess invitation was accepted.\n\n"
            "You are playing White, so it is your turn.\n\n"
            "Reply to this email with your first move on the first line.\n\n"
            "Examples:\n"
            "e4\n"
            "d4\n"
            "Nf3\n\n"
            f"{delay_description}"
        ),
        reply_address=reply_address,
    )

    black_email = PreparedEmail(
        recipient=updated_game.black_email,
        subject=f"[Chesspost {short_code}] Game started",
        body=(
            "The chess invitation was accepted.\n\n"
            "You are playing Black.\n\n"
            "White moves first. Chesspost will email you when it is "
            "your turn.\n\n"
            f"{delay_description}"
        ),
        reply_address=reply_address,
    )

    return InvitationDecisionResult(
        processed=True,
        decision="accept",
        game=updated_game,
        emails=(
            white_email,
            black_email,
        ),
    )
