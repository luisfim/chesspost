from board_renderer import render_board_png
from chess_engine import apply_move, new_game_fen


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_render_starting_board_as_png(tmp_path) -> None:
    output_path = tmp_path / "starting-board.png"

    result_path = render_board_png(
        new_game_fen(),
        output_path,
    )

    assert result_path == output_path
    assert output_path.exists()
    assert output_path.read_bytes().startswith(PNG_SIGNATURE)


def test_render_board_after_move(tmp_path) -> None:
    move_result = apply_move(new_game_fen(), "e4")
    output_path = tmp_path / "after-e4.png"

    render_board_png(
        move_result.fen,
        output_path,
        orientation="black",
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 1000


def test_create_missing_output_directory(tmp_path) -> None:
    output_path = tmp_path / "boards" / "game" / "board.png"

    render_board_png(
        new_game_fen(),
        output_path,
    )

    assert output_path.exists()


def test_reject_invalid_orientation(tmp_path) -> None:
    output_path = tmp_path / "board.png"

    try:
        render_board_png(
            new_game_fen(),
            output_path,
            orientation="sideways",
        )
    except ValueError as error:
        assert str(error) == (
            'Orientation must be either "white" or "black".'
        )
    else:
        raise AssertionError("Expected invalid orientation to be rejected")
