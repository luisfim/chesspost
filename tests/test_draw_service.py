from database import create_game
from draw_service import (
    accept_draw,
    decline_draw,
    get_draw_offer,
    offer_draw,
)


def test_player_can_offer_draw(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    result = offer_draw(
        game.code,
        "white@example.com",
        database_path,
    )

    assert result.accepted is True

    offer = get_draw_offer(
        game.code,
        database_path,
    )

    assert offer is not None
    assert offer.offered_by_email == "white@example.com"


def test_opponent_can_decline_draw(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    offer_draw(
        game.code,
        "white@example.com",
        database_path,
    )

    result = decline_draw(
        game.code,
        "black@example.com",
        database_path,
    )

    assert result.accepted is True
    assert get_draw_offer(
        game.code,
        database_path,
    ) is None


def test_opponent_can_accept_draw(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    offer_draw(
        game.code,
        "white@example.com",
        database_path,
    )

    result = accept_draw(
        game.code,
        "black@example.com",
        database_path,
    )

    assert result.accepted is True
    assert result.game.status == "finished"
    assert result.game.result == "1/2-1/2"


def test_player_cannot_accept_own_draw_offer(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    offer_draw(
        game.code,
        "white@example.com",
        database_path,
    )

    result = accept_draw(
        game.code,
        "white@example.com",
        database_path,
    )

    assert result.accepted is False
    assert "own draw offer" in result.message
