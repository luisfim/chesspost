from new_game_parser import parse_new_game_email


def test_parse_default_new_game_email() -> None:
    result = parse_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="",
    )

    assert result.valid is True
    assert result.sender_email == "luis@example.com"
    assert result.opponent_email == "friend@example.com"
    assert result.color == "random"
    assert result.delay_hours == 0


def test_parse_new_game_with_options() -> None:
    result = parse_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="""
        color: white
        delay: 24h
        """,
    )

    assert result.valid is True
    assert result.color == "white"
    assert result.delay_hours == 24


def test_email_addresses_are_normalized() -> None:
    result = parse_new_game_email(
        sender_email="  LUIS@EXAMPLE.COM ",
        subject=" FRIEND@EXAMPLE.COM ",
        body="color: BLACK",
    )

    assert result.valid is True
    assert result.sender_email == "luis@example.com"
    assert result.opponent_email == "friend@example.com"
    assert result.color == "black"


def test_immediate_delay_is_supported() -> None:
    result = parse_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="delay: immediate",
    )

    assert result.valid is True
    assert result.delay_hours == 0


def test_invalid_opponent_email_is_rejected() -> None:
    result = parse_new_game_email(
        sender_email="luis@example.com",
        subject="not-an-email",
        body="",
    )

    assert result.valid is False
    assert result.opponent_email is None
    assert "subject" in result.message.lower()


def test_player_cannot_challenge_same_email() -> None:
    result = parse_new_game_email(
        sender_email="luis@example.com",
        subject="luis@example.com",
        body="",
    )

    assert result.valid is False
    assert "own email" in result.message


def test_invalid_color_is_rejected() -> None:
    result = parse_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="color: green",
    )

    assert result.valid is False
    assert "white" in result.message


def test_excessive_delay_is_rejected() -> None:
    result = parse_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body="delay: 1000h",
    )

    assert result.valid is False
    assert "720 hours" in result.message
