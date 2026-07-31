from invitation_service import process_new_game_email


def test_create_invitation_with_white_inviter(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    response = process_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="color: white",
        db_path=database_path,
    )

    assert response.request_accepted is True
    assert response.recipient == "friend@example.com"
    assert response.game is not None
    assert response.game.status == "invited"
    assert response.game.white_email == "luis@example.com"
    assert response.game.black_email == "friend@example.com"
    assert response.game.invited_by_email == "luis@example.com"
    assert "You will play Black" in response.body
    assert response.reply_address is not None


def test_create_invitation_with_black_inviter(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    response = process_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="color: black",
        db_path=database_path,
    )

    assert response.request_accepted is True
    assert response.game is not None
    assert response.game.white_email == "friend@example.com"
    assert response.game.black_email == "luis@example.com"
    assert "You will play White" in response.body


def test_invitation_stores_delivery_delay(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    response = process_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="""
        color: white
        delay: 24h
        """,
        db_path=database_path,
    )

    assert response.request_accepted is True
    assert response.game is not None
    assert response.game.delivery_delay_hours == 24
    assert "after 24 hours" in response.body


def test_random_color_assigns_both_players(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    response = process_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="",
        db_path=database_path,
    )

    assert response.request_accepted is True
    assert response.game is not None

    assigned_players = {
        response.game.white_email,
        response.game.black_email,
    }

    assert assigned_players == {
        "luis@example.com",
        "friend@example.com",
    }


def test_invalid_request_returns_error_to_sender(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    response = process_new_game_email(
        sender_email="luis@example.com",
        subject="not-an-email",
        body="",
        db_path=database_path,
    )

    assert response.request_accepted is False
    assert response.recipient == "luis@example.com"
    assert response.game is None
    assert response.reply_address is None
    assert "could not be created" in response.subject
