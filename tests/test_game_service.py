from database import create_game
from game_service import submit_move


def test_white_can_make_first_move(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    result = submit_move(
        game.code,
        "white@example.com",
        "e4",
        database_path,
    )

    assert result.accepted is True
    assert result.move == "e4"
    assert result.game.fen != game.fen


def test_black_cannot_move_first(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    result = submit_move(
        game.code,
        "black@example.com",
        "e5",
        database_path,
    )

    assert result.accepted is False
    assert result.message == "It is White's turn."
    assert result.game.fen == game.fen


def test_unknown_email_cannot_play(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    result = submit_move(
        game.code,
        "stranger@example.com",
        "e4",
        database_path,
    )

    assert result.accepted is False
    assert result.message == (
        "This email address is not a player in this game."
    )


def test_illegal_move_does_not_change_game(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    result = submit_move(
        game.code,
        "white@example.com",
        "e5",
        database_path,
    )

    assert result.accepted is False
    assert result.game.fen == game.fen


def test_players_can_alternate_moves(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    white_result = submit_move(
        game.code,
        "white@example.com",
        "e4",
        database_path,
    )

    black_result = submit_move(
        game.code,
        "black@example.com",
        "e5",
        database_path,
    )

    assert white_result.accepted is True
    assert black_result.accepted is True
    assert black_result.move == "e5"
