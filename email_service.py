from dataclasses import dataclass
from pathlib import Path

from database import DATABASE_PATH, Game, get_game
from email_parser import parse_email_body
from game_service import submit_move


@dataclass(frozen=True)
class EmailResponse:
    recipient: str
    subject: str
    body: str
    delivered_to_opponent: bool
    move: str | None


def get_opponent(game: Game, sender_email: str) -> str:
    """Return the opponent of the sender."""
    sender_email = sender_email.strip().lower()

    if sender_email == game.white_email:
        return game.black_email

    if sender_email == game.black_email:
        return game.white_email

    raise ValueError("The sender is not a player in this game.")


def error_response(
    sender_email: str,
    game_code: str,
    message: str,
) -> EmailResponse:
    """Create an email that returns an error to the sender."""
    short_code = game_code[:8].upper()

    return EmailResponse(
        recipient=sender_email,
        subject=f"[Chesspost {short_code}] Move not accepted",
        body=(
            f"{message}\n\n"
            "Your opponent did not receive this move.\n\n"
            "Reply again with a legal move."
        ),
        delivered_to_opponent=False,
        move=None,
    )


def process_game_email(
    game_code: str,
    sender_email: str,
    email_body: str,
    db_path: Path = DATABASE_PATH,
) -> EmailResponse:
    """Process one email sent to an existing Chesspost game."""
    sender_email = sender_email.strip().lower()
    game = get_game(game_code, db_path)

    if game is None:
        return error_response(
            sender_email,
            game_code,
            "This Chesspost game could not be found.",
        )

    parsed_email = parse_email_body(email_body)

    if not parsed_email.valid:
        return error_response(
            sender_email,
            game_code,
            parsed_email.message,
        )

    if parsed_email.command != "move":
        return error_response(
            sender_email,
            game_code,
            (
                f'The command "{parsed_email.command}" is recognized, '
                "but it has not been implemented yet."
            ),
        )

    if parsed_email.value is None:
        return error_response(
            sender_email,
            game_code,
            "No chess move was found in the email.",
        )

    submission = submit_move(
        game_code=game_code,
        sender_email=sender_email,
        move_text=parsed_email.value,
        db_path=db_path,
    )

    if not submission.accepted:
        return error_response(
            sender_email,
            game_code,
            submission.message,
        )

    opponent = get_opponent(submission.game, sender_email)
    short_code = game_code[:8].upper()

    return EmailResponse(
        recipient=opponent,
        subject=f"[Chesspost {short_code}] {submission.move}",
        body=(
            f"{sender_email} played {submission.move}.\n\n"
            "It is now your turn.\n\n"
            "Reply to this email with your move on the first line."
        ),
        delivered_to_opponent=True,
        move=submission.move,
    )
