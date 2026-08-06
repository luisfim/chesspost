from database import create_game
from thread_store import (
    build_reply_headers,
    get_thread_context,
    normalize_references,
    save_thread_context,
)


def test_normalize_reference_string() -> None:
    result = normalize_references(
        "<first@example.com> <second@example.com>"
    )

    assert result == (
        "<first@example.com>",
        "<second@example.com>",
    )


def test_duplicate_references_are_removed() -> None:
    result = normalize_references(
        [
            "<first@example.com>",
            "<first@example.com> <second@example.com>",
        ]
    )

    assert result == (
        "<first@example.com>",
        "<second@example.com>",
    )


def test_save_player_thread_context(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    saved = save_thread_context(
        game_code=game.code,
        player_email="white@example.com",
        message_id="<white-move-1@example.com>",
        references="<game-start@example.com>",
        db_path=database_path,
    )

    assert saved.last_message_id == (
        "<white-move-1@example.com>"
    )
    assert saved.references == (
        "<game-start@example.com>",
        "<white-move-1@example.com>",
    )


def test_retrieve_saved_thread_context(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    save_thread_context(
        game_code=game.code,
        player_email="black@example.com",
        message_id="<black-accept@example.com>",
        db_path=database_path,
    )

    context = get_thread_context(
        game.code,
        "black@example.com",
        database_path,
    )

    assert context is not None
    assert context.player_email == "black@example.com"
    assert context.references == (
        "<black-accept@example.com>",
    )


def test_new_message_replaces_latest_context(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    save_thread_context(
        game_code=game.code,
        player_email="white@example.com",
        message_id="<white-move-1@example.com>",
        db_path=database_path,
    )

    updated = save_thread_context(
        game_code=game.code,
        player_email="white@example.com",
        message_id="<white-move-2@example.com>",
        references=(
            "<game-start@example.com> "
            "<white-move-1@example.com>"
        ),
        db_path=database_path,
    )

    assert updated.last_message_id == (
        "<white-move-2@example.com>"
    )
    assert updated.references == (
        "<game-start@example.com>",
        "<white-move-1@example.com>",
        "<white-move-2@example.com>",
    )


def test_build_reply_headers(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    save_thread_context(
        game_code=game.code,
        player_email="white@example.com",
        message_id="<white-move@example.com>",
        references="<game-start@example.com>",
        db_path=database_path,
    )

    headers = build_reply_headers(
        game.code,
        "white@example.com",
        database_path,
    )

    assert headers == {
        "In-Reply-To": "<white-move@example.com>",
        "References": (
            "<game-start@example.com> "
            "<white-move@example.com>"
        ),
    }


def test_player_without_context_has_no_headers(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    headers = build_reply_headers(
        game.code,
        "white@example.com",
        database_path,
    )

    assert headers == {}


def test_outsider_context_is_rejected(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    try:
        save_thread_context(
            game_code=game.code,
            player_email="stranger@example.com",
            message_id="<stranger@example.com>",
            db_path=database_path,
        )
    except ValueError as error:
        assert "not a player" in str(error)
    else:
        raise AssertionError(
            "Expected the outsider to be rejected."
        )


def test_normalize_thread_subject() -> None:
    from thread_store import normalize_thread_subject

    assert normalize_thread_subject(
        "Re: RE: Fwd: Chess invitation"
    ) == "Chess invitation"


def test_save_and_build_reply_subject(tmp_path) -> None:
    from thread_store import build_reply_subject

    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    save_thread_context(
        game_code=game.code,
        player_email="white@example.com",
        message_id="<white@example.com>",
        subject="Re: Original Chesspost Thread",
        db_path=database_path,
    )

    context = get_thread_context(
        game.code,
        "white@example.com",
        database_path,
    )

    assert context is not None
    assert context.subject == "Original Chesspost Thread"

    assert build_reply_subject(
        game.code,
        "white@example.com",
        database_path,
    ) == "Re: Original Chesspost Thread"
