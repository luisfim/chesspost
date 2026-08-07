from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import chess

from chess_engine import apply_move
from database import DATABASE_PATH, Game, connect, get_game


@dataclass(frozen=True)
class SubmissionResult:
    accepted: bool
    message: str
    game: Game
    move: str | None


def submit_move(
    game_code: str,
    sender_email: str,
    move_text: str,
    db_path: Path = DATABASE_PATH,
) -> SubmissionResult:
    """Validate and save one move submitted by email."""
    game = get_game(game_code, db_path)

    if game is None:
        raise ValueError("Game not found.")

    sender_email = sender_email.strip().lower()

    if game.status != "active":
        return SubmissionResult(
            accepted=False,
            message="This game has already finished.",
            game=game,
            move=None,
        )

    board = chess.Board(game.fen)

    expected_email = (
        game.white_email
        if board.turn == chess.WHITE
        else game.black_email
    )

    if sender_email not in {game.white_email, game.black_email}:
        return SubmissionResult(
            accepted=False,
            message="This email address is not a player in this game.",
            game=game,
            move=None,
        )

    if sender_email != expected_email:
        color = "White" if board.turn == chess.WHITE else "Black"

        return SubmissionResult(
            accepted=False,
            message=f"It is {color}'s turn.",
            game=game,
            move=None,
        )

    move_result = apply_move(game.fen, move_text)

    if not move_result.accepted:
        return SubmissionResult(
            accepted=False,
            message=move_result.message,
            game=game,
            move=None,
        )

    now = datetime.now(timezone.utc).isoformat()
    status = "finished" if move_result.game_over else "active"

    with connect(db_path) as connection:
        next_ply = connection.execute(
            """
            SELECT COALESCE(MAX(ply), 0) + 1
            FROM moves
            WHERE game_code = ?
            """,
            (game.code,),
        ).fetchone()[0]

        connection.execute(
            """
            INSERT INTO moves (
                game_code,
                ply,
                player_email,
                san,
                fen_before,
                fen_after,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game.code,
                next_ply,
                sender_email,
                move_result.move,
                game.fen,
                move_result.fen,
                now,
            ),
        )

        connection.execute(
            """
            UPDATE games
            SET
                fen = ?,
                status = ?,
                result = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (
                move_result.fen,
                status,
                move_result.result,
                now,
                game.code,
            ),
        )

    updated_game = get_game(game.code, db_path)

    if updated_game is None:
        raise RuntimeError("The updated game could not be loaded.")

    return SubmissionResult(
        accepted=True,
        message=move_result.message,
        game=updated_game,
        move=move_result.move,
    )


def resign_game(
    game_code: str,
    sender_email: str,
    db_path: Path = DATABASE_PATH,
) -> SubmissionResult:
    """End an active game by resignation."""
    game = get_game(game_code, db_path)

    if game is None:
        raise ValueError("Game not found.")

    sender_email = sender_email.strip().lower()

    if sender_email not in {
        game.white_email,
        game.black_email,
    }:
        return SubmissionResult(
            accepted=False,
            message="This email address is not a player in this game.",
            game=game,
            move=None,
        )

    if game.status != "active":
        return SubmissionResult(
            accepted=False,
            message="This game has already finished.",
            game=game,
            move=None,
        )

    result = (
        "0-1"
        if sender_email == game.white_email
        else "1-0"
    )

    now = datetime.now(timezone.utc).isoformat()

    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE games
            SET
                status = 'finished',
                result = ?,
                updated_at = ?
            WHERE code = ?
            """,
            (
                result,
                now,
                game.code,
            ),
        )

    updated_game = get_game(
        game.code,
        db_path,
    )

    if updated_game is None:
        raise RuntimeError(
            "The resigned game could not be loaded."
        )

    return SubmissionResult(
        accepted=True,
        message="Resignation accepted.",
        game=updated_game,
        move=None,
    )
