from database import create_game
from game_mailbox import (
    ensure_game_mailboxes,
    game_email_address,
    game_has_secure_mailboxes,
    get_game_mailbox,
    resolve_game_email_address,
)


def test_game_gets_different_mailbox_for_each_player(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    white, black = ensure_game_mailboxes(
        game,
        database_path,
    )

    assert white.player_email == "white@example.com"
    assert black.player_email == "black@example.com"

    assert white.token != black.token

    assert game_has_secure_mailboxes(
        game.code,
        database_path,
    )


def test_player_address_is_stable(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    first = game_email_address(
        game.code,
        "white@example.com",
        database_path,
    )

    second = game_email_address(
        game.code,
        "white@example.com",
        database_path,
    )

    assert first == second


def test_players_receive_different_addresses(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    white_address = game_email_address(
        game.code,
        "white@example.com",
        database_path,
    )

    black_address = game_email_address(
        game.code,
        "black@example.com",
        database_path,
    )

    assert white_address != black_address

    assert game.code in white_address
    assert game.code in black_address


def test_secure_address_resolves_to_correct_player(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    white_address = game_email_address(
        game.code,
        "white@example.com",
        database_path,
    )

    resolved = resolve_game_email_address(
        white_address,
        database_path,
    )

    assert resolved is not None
    assert resolved.secure is True
    assert resolved.game.code == game.code
    assert resolved.player_email == "white@example.com"


def test_invalid_secret_token_is_rejected(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    address = game_email_address(
        game.code,
        "white@example.com",
        database_path,
    )

    local, domain = address.split("@", 1)

    tampered = (
        local[:-1]
        + (
            "0"
            if local[-1] != "0"
            else "1"
        )
        + "@"
        + domain
    )

    resolved = resolve_game_email_address(
        tampered,
        database_path,
    )

    assert resolved is None


def test_legacy_address_works_for_old_game(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    legacy = (
        f"game-{game.code}"
        "@chesspost.test"
    )

    resolved = resolve_game_email_address(
        legacy,
        database_path,
    )

    assert resolved is not None
    assert resolved.secure is False
    assert resolved.game.code == game.code
    assert resolved.player_email is None


def test_legacy_address_is_disabled_after_secure_upgrade(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    ensure_game_mailboxes(
        game,
        database_path,
    )

    legacy = (
        f"game-{game.code}"
        "@chesspost.test"
    )

    resolved = resolve_game_email_address(
        legacy,
        database_path,
    )

    assert resolved is None


def test_mailbox_can_be_loaded_from_database(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    ensure_game_mailboxes(
        game,
        database_path,
    )

    mailbox = get_game_mailbox(
        game.code,
        "black@example.com",
        database_path,
    )

    assert mailbox is not None
    assert mailbox.player_email == "black@example.com"
    assert len(mailbox.token) == 24
