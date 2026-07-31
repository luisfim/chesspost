from database import create_game, get_game, init_database


def test_create_and_retrieve_game(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    init_database(database_path)

    created_game = create_game(
        white_email="white@example.com",
        black_email="black@example.com",
        db_path=database_path,
    )

    retrieved_game = get_game(created_game.code, database_path)

    assert retrieved_game is not None
    assert retrieved_game.code == created_game.code
    assert retrieved_game.white_email == "white@example.com"
    assert retrieved_game.black_email == "black@example.com"
    assert retrieved_game.status == "active"
    assert retrieved_game.result is None


def test_unknown_game_returns_none(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    init_database(database_path)

    assert get_game("does-not-exist", database_path) is None


def test_players_must_have_different_emails(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    try:
        create_game(
            white_email="player@example.com",
            black_email="player@example.com",
            db_path=database_path,
        )
    except ValueError as error:
        assert str(error) == (
            "A player cannot play against the same email address."
        )
    else:
        raise AssertionError("Expected create_game to raise ValueError")
