from dataclasses import dataclass

import chess


@dataclass(frozen=True)
class MoveResult:
    accepted: bool
    message: str
    fen: str
    move: str | None
    game_over: bool
    result: str | None


def new_game_fen() -> str:
    """Return the standard starting chess position."""
    return chess.Board().fen()


def apply_move(fen: str, move_text: str) -> MoveResult:
    """Validate and apply one move to a position."""
    board = chess.Board(fen)
    move_text = move_text.strip()

    if not move_text:
        return MoveResult(
            accepted=False,
            message="No move was provided.",
            fen=fen,
            move=None,
            game_over=False,
            result=None,
        )

    try:
        move = board.parse_san(move_text)
    except ValueError:
        turn = "White" if board.turn == chess.WHITE else "Black"

        return MoveResult(
            accepted=False,
            message=f'"{move_text}" is not a legal move. It is {turn}\'s turn.',
            fen=fen,
            move=None,
            game_over=False,
            result=None,
        )

    canonical_move = board.san(move)
    board.push(move)

    game_over = board.is_game_over(claim_draw=True)
    result = board.result(claim_draw=True) if game_over else None

    return MoveResult(
        accepted=True,
        message=f"Move accepted: {canonical_move}",
        fen=board.fen(),
        move=canonical_move,
        game_over=game_over,
        result=result,
    )
