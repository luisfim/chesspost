from database import create_game
from email_service import process_game_email


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_legal_move_is_sent_to_opponent_with_board(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    attachment_directory = tmp_path / "boards"

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
        attachment_directory,
    )

    assert response.delivered_to_opponent is True
    assert response.recipient == "black@example.com"
    assert response.move == "e4"
    assert response.delay_hours == 0
    assert "white@example.com played e4" in response.body

    assert response.attachment_path is not None
    assert response.attachment_path.exists()
    assert response.attachment_path.read_bytes().startswith(PNG_SIGNATURE)


def test_board_is_oriented_for_white_recipient(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    attachment_directory = tmp_path / "boards"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    first_response = process_game_email(
        game.code,
        "white@example.com",
        "e4",
        database_path,
        attachment_directory,
    )

    assert first_response.delivered_to_opponent is True

    second_response = process_game_email(
        game.code,
        "black@example.com",
        "e5",
        database_path,
        attachment_directory,
    )

    assert second_response.delivered_to_opponent is True
    assert second_response.recipient == "white@example.com"
    assert second_response.attachment_path is not None
    assert second_response.attachment_path.exists()


def test_move_with_delay_preserves_delay_setting(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    attachment_directory = tmp_path / "boards"

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

        delay: 24h
        """,
        database_path,
        attachment_directory,
    )

    assert response.delivered_to_opponent is True
    assert response.delay_hours == 24
    assert "after 24 hours" in response.body


def test_illegal_move_returns_to_sender_without_board(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    attachment_directory = tmp_path / "boards"

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
        attachment_directory,
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "white@example.com"
    assert response.move is None
    assert response.attachment_path is None
    assert response.delay_hours is None
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
        tmp_path / "boards",
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "black@example.com"
    assert response.attachment_path is None
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
        tmp_path / "boards",
    )

    assert response.delivered_to_opponent is True
    assert response.move == "e4"
    assert response.attachment_path is not None


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
        tmp_path / "boards",
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "white@example.com"
    assert response.attachment_path is None
    assert "not been implemented yet" in response.body


def test_unknown_game_returns_to_sender(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    response = process_game_email(
        "unknown-game",
        "player@example.com",
        "e4",
        database_path,
        tmp_path / "boards",
    )

    assert response.delivered_to_opponent is False
    assert response.recipient == "player@example.com"
    assert response.attachment_path is None
    assert "could not be found" in response.body


def test_game_default_delay_is_used_for_move(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    attachment_directory = tmp_path / "boards"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
        delivery_delay_hours=24,
    )

    response = process_game_email(
        game.code,
        "white@example.com",
        "e4",
        database_path,
        attachment_directory,
    )

    assert response.delivered_to_opponent is True
    assert response.delay_hours == 24
    assert "after 24 hours" in response.body


def test_per_move_delay_overrides_game_default(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    attachment_directory = tmp_path / "boards"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
        delivery_delay_hours=24,
    )

    response = process_game_email(
        game.code,
        "white@example.com",
        """
        e4

        delay: 2h
        """,
        database_path,
        attachment_directory,
    )

    assert response.delivered_to_opponent is True
    assert response.delay_hours == 2
    assert "after 2 hours" in response.body


def test_immediate_game_stays_immediate(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    attachment_directory = tmp_path / "boards"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
        delivery_delay_hours=0,
    )

    response = process_game_email(
        game.code,
        "white@example.com",
        "e4",
        database_path,
        attachment_directory,
    )

    assert response.delay_hours == 0
    assert "delivered immediately" in response.body
