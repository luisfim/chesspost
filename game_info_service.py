from dataclasses import dataclass
from pathlib import Path

from database import DATABASE_PATH, connect, get_game
from email_service import create_board_attachment


@dataclass(frozen=True)
class GameInfoResponse:
    accepted: bool
    recipient: str
    subject: str
    body: str
    attachment_path: Path | None


def _load_player_game(
    game_code: str,
    sender_email: str,
    db_path: Path,
):
    game = get_game(
        game_code,
        db_path,
    )

    if game is None:
        return None, "Game not found."

    sender_email = sender_email.strip().lower()

    if sender_email not in {
        game.white_email,
        game.black_email,
    }:
        return (
            None,
            "This email address is not a player in this game.",
        )

    return game, None


def build_help_response(
    game_code: str,
    sender_email: str,
    db_path: Path = DATABASE_PATH,
) -> GameInfoResponse:
    """Return commands available to a player."""
    game, error = _load_player_game(
        game_code,
        sender_email,
        db_path,
    )

    short_code = game_code[:8].upper()

    if game is None:
        return GameInfoResponse(
            accepted=False,
            recipient=sender_email,
            subject=f"[Chesspost {short_code}] Help",
            body=error or "Game not found.",
            attachment_path=None,
        )

    if game.status == "active":
        commands = (
            "Available commands:\n\n"
            "<move>        Play a move, for example: e4 or Nf3\n"
            "show board    Send the current board\n"
            "show moves    Send the move history\n"
            "offer draw    Offer your opponent a draw\n"
            "accept draw   Accept a pending draw offer\n"
            "decline draw  Decline a pending draw offer\n"
            "resign        Resign the game\n"
            "help          Show this message"
        )

    elif game.status == "finished":
        commands = (
            "This game has finished.\n\n"
            "Available commands:\n\n"
            "show board    Send the final board\n"
            "show moves    Send the complete move history\n"
            "rematch       Request another game\n"
            "help          Show this message"
        )

    else:
        commands = (
            f"Game status: {game.status}\n\n"
            "Available commands:\n\n"
            "show board    Send the current board\n"
            "show moves    Send the move history\n"
            "help          Show this message"
        )

    return GameInfoResponse(
        accepted=True,
        recipient=sender_email,
        subject=f"[Chesspost {short_code}] Help",
        body=commands,
        attachment_path=None,
    )


def build_board_response(
    game_code: str,
    sender_email: str,
    attachment_directory: Path,
    db_path: Path = DATABASE_PATH,
) -> GameInfoResponse:
    """Send the current board only to the requesting player."""
    game, error = _load_player_game(
        game_code,
        sender_email,
        db_path,
    )

    short_code = game_code[:8].upper()

    if game is None:
        return GameInfoResponse(
            accepted=False,
            recipient=sender_email,
            subject=f"[Chesspost {short_code}] Board",
            body=error or "Game not found.",
            attachment_path=None,
        )

    attachment_path = create_board_attachment(
        game=game,
        recipient_email=sender_email,
        attachment_directory=attachment_directory,
    )

    return GameInfoResponse(
        accepted=True,
        recipient=sender_email,
        subject=f"[Chesspost {short_code}] Current board",
        body=(
            "Here is the current position.\n\n"
            f"Game status: {game.status}\n"
            f"Result: {game.result or '-'}"
        ),
        attachment_path=attachment_path,
    )


def format_move_history(
    game_code: str,
    db_path: Path = DATABASE_PATH,
) -> str:
    """Return the move list in a compact PGN-like form."""
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                ply,
                san
            FROM moves
            WHERE game_code = ?
            ORDER BY ply ASC
            """,
            (game_code,),
        ).fetchall()

    if not rows:
        return "No moves have been played yet."

    lines: list[str] = []

    for row in rows:
        ply = int(row["ply"])
        san = row["san"]

        if ply % 2 == 1:
            move_number = (ply + 1) // 2
            lines.append(
                f"{move_number}. {san}"
            )
        else:
            lines[-1] += f" {san}"

    return "\n".join(lines)


def build_moves_response(
    game_code: str,
    sender_email: str,
    db_path: Path = DATABASE_PATH,
) -> GameInfoResponse:
    """Send the game's complete move history."""
    game, error = _load_player_game(
        game_code,
        sender_email,
        db_path,
    )

    short_code = game_code[:8].upper()

    if game is None:
        return GameInfoResponse(
            accepted=False,
            recipient=sender_email,
            subject=f"[Chesspost {short_code}] Moves",
            body=error or "Game not found.",
            attachment_path=None,
        )

    history = format_move_history(
        game.code,
        db_path,
    )

    return GameInfoResponse(
        accepted=True,
        recipient=sender_email,
        subject=f"[Chesspost {short_code}] Move history",
        body=(
            "Move history\n"
            "------------\n\n"
            f"{history}\n\n"
            f"Status: {game.status}\n"
            f"Result: {game.result or '-'}"
        ),
        attachment_path=None,
    )
