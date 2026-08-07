from database import create_game
from game_info_service import (
    build_board_response,
    build_help_response,
    build_moves_response,
    format_move_history,
)
from game_service import submit_move


def test_help_is_returned_to_player(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = build_help_response(
        game.code,
        "white@example.com",
        database_path,
    )

    assert response.accepted is True
    assert response.recipient == "white@example.com"
    assert "show board" in response.body
    assert "show moves" in response.body
    assert "resign" in response.body


def test_show_board_creates_attachment(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"
    boards = tmp_path / "boards"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = build_board_response(
        game.code,
        "black@example.com",
        boards,
        database_path,
    )

    assert response.accepted is True
    assert response.recipient == "black@example.com"
    assert response.attachment_path is not None
    assert response.attachment_path.exists()


def test_move_history_is_formatted(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    submit_move(
        game.code,
        "white@example.com",
        "e4",
        database_path,
    )

    submit_move(
        game.code,
        "black@example.com",
        "e5",
        database_path,
    )

    submit_move(
        game.code,
        "white@example.com",
        "Nf3",
        database_path,
    )

    history = format_move_history(
        game.code,
        database_path,
    )

    assert history == (
        "1. e4 e5\n"
        "2. Nf3"
    )


def test_show_moves_returns_only_to_requester(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    submit_move(
        game.code,
        "white@example.com",
        "d4",
        database_path,
    )

    response = build_moves_response(
        game.code,
        "black@example.com",
        database_path,
    )

    assert response.accepted is True
    assert response.recipient == "black@example.com"
    assert "1. d4" in response.body


def test_non_player_cannot_request_game_information(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = build_help_response(
        game.code,
        "intruder@example.com",
        database_path,
    )

    assert response.accepted is False
    assert "not a player" in response.body
