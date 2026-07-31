from database import create_game
from email_service import process_game_email


def test_legal_move_is_sent_to_opponent(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = process_game_email(
        game.code,
        "white@example.com",
        "e4",
        database_path,
    )

    assert response.delivered_to_opponent is True
    assert response.recipient == "black@example.com"
    assert response.move == "e4"
    assert "white@example.com played e4" in response.body


def test_illegal_move_returns_to_sender(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = process_game_email(
        game.code,
        "white@example.com",
        "e5",
        database_path,
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "white@example.com"
    assert response.move is None
    assert "did not receive this move" in response.body


def test_wrong_player_turn_returns_to_sender(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = process_game_email(
        game.code,
        "black@example.com",
        "e5",
        database_path,
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "black@example.com"
    assert "White's turn" in response.body


def test_email_signature_and_quote_are_ignored(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = process_game_email(
        game.code,
        "white@example.com",
        """
        e4

        On Friday, Chesspost wrote:
        > Reply with your move.
        """,
        database_path,
    )

    assert response.delivered_to_opponent is True
    assert response.move == "e4"


def test_unimplemented_command_returns_to_sender(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = process_game_email(
        game.code,
        "white@example.com",
        "help",
        database_path,
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "white@example.com"
    assert "not been implemented yet" in response.body


def test_unknown_game_returns_to_sender(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    response = process_game_email(
        "unknown-game",
        "player@example.com",
        "e4",
        database_path,
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "player@example.com"
    assert "could not be found" in response.body
