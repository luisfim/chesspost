from pathlib import Path

import cairosvg
import chess
import chess.svg


def render_board_png(
    fen: str,
    output_path: str | Path,
    orientation: str = "white",
    size: int = 600,
) -> Path:
    """Render a chess position as a PNG image."""
    if orientation not in {"white", "black"}:
        raise ValueError('Orientation must be either "white" or "black".')

    if size < 100:
        raise ValueError("Board size must be at least 100 pixels.")

    board = chess.Board(fen)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chess_orientation = (
        chess.WHITE if orientation == "white" else chess.BLACK
    )

    svg_image = chess.svg.board(
        board=board,
        orientation=chess_orientation,
        coordinates=True,
        borders=True,
        size=size,
    )

    cairosvg.svg2png(
        bytestring=svg_image.encode("utf-8"),
        write_to=str(output_path),
    )

    return output_path
