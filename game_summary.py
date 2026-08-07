from dataclasses import dataclass
from pathlib import Path

import chess

from database import DATABASE_PATH, Game, connect


@dataclass(frozen=True)
class GameSummary:
    result: str
    winner_email: str | None
    loser_email: str | None
    plies: int
    move_number: int
    white_wins: int
    black_wins: int
    draws: int
    termination: str


def get_move_count(
    game_code: str,
    db_path: Path = DATABASE_PATH,
) -> int:
    """Return the number of half-moves stored for a game."""
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM moves
            WHERE game_code = ?
            """,
            (game_code,),
        ).fetchone()

    return int(row[0])


def get_winner(
    game: Game,
) -> tuple[str | None, str | None]:
    """Return winner and loser emails from the PGN-style result."""
    if game.result == "1-0":
        return game.white_email, game.black_email

    if game.result == "0-1":
        return game.black_email, game.white_email

    return None, None


def describe_termination(
    game: Game,
    fallback: str = "Game over",
) -> str:
    """Describe how a board position ended."""
    board = chess.Board(game.fen)
    outcome = board.outcome(claim_draw=True)

    if outcome is None:
        return fallback

    labels = {
        chess.Termination.CHECKMATE: "Checkmate",
        chess.Termination.STALEMATE: "Stalemate",
        chess.Termination.INSUFFICIENT_MATERIAL:
            "Draw by insufficient material",
        chess.Termination.SEVENTYFIVE_MOVES:
            "Draw by the seventy-five-move rule",
        chess.Termination.FIVEFOLD_REPETITION:
            "Draw by fivefold repetition",
        chess.Termination.FIFTY_MOVES:
            "Draw by the fifty-move rule",
        chess.Termination.THREEFOLD_REPETITION:
            "Draw by threefold repetition",
    }

    return labels.get(
        outcome.termination,
        fallback,
    )


def get_head_to_head(
    game: Game,
    db_path: Path = DATABASE_PATH,
) -> tuple[int, int, int]:
    """
    Return wins for game.white_email, wins for game.black_email, draws.

    Color does not matter across previous games.
    """
    player_a = game.white_email
    player_b = game.black_email

    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                white_email,
                black_email,
                result
            FROM games
            WHERE status = 'finished'
              AND (
                    (white_email = ? AND black_email = ?)
                 OR (white_email = ? AND black_email = ?)
              )
            """,
            (
                player_a,
                player_b,
                player_b,
                player_a,
            ),
        ).fetchall()

    player_a_wins = 0
    player_b_wins = 0
    draws = 0

    for row in rows:
        result = row["result"]

        if result == "1/2-1/2":
            draws += 1
            continue

        if result not in {"1-0", "0-1"}:
            continue

        winner = (
            row["white_email"]
            if result == "1-0"
            else row["black_email"]
        )

        if winner == player_a:
            player_a_wins += 1
        elif winner == player_b:
            player_b_wins += 1

    return player_a_wins, player_b_wins, draws


def summarize_game(
    game: Game,
    db_path: Path = DATABASE_PATH,
    *,
    termination_override: str | None = None,
) -> GameSummary:
    """Build the final summary for a finished game."""
    plies = get_move_count(
        game.code,
        db_path,
    )

    move_number = (plies + 1) // 2
    winner, loser = get_winner(game)

    white_wins, black_wins, draws = get_head_to_head(
        game,
        db_path,
    )

    termination = (
        termination_override
        or describe_termination(game)
    )

    return GameSummary(
        result=game.result or "*",
        winner_email=winner,
        loser_email=loser,
        plies=plies,
        move_number=move_number,
        white_wins=white_wins,
        black_wins=black_wins,
        draws=draws,
        termination=termination,
    )


def build_final_email_body(
    game: Game,
    summary: GameSummary,
) -> str:
    """Create the final human-readable game report."""
    if summary.winner_email is None:
        result_text = "The game ended in a draw."
    else:
        result_text = (
            f"{summary.winner_email} wins."
        )

    return (
        f"{summary.termination}\n\n"
        f"{result_text}\n\n"
        f"Result: {summary.result}\n"
        f"Moves: {summary.move_number}\n\n"
        "Head-to-head record:\n"
        f"{game.white_email}: {summary.white_wins} wins\n"
        f"{game.black_email}: {summary.black_wins} wins\n"
        f"Draws: {summary.draws}\n\n"
        "Reply with:\n\n"
        "rematch\n\n"
        "to start another game with the same opponent."
    )
