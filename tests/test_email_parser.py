from email_parser import extract_new_lines, parse_email_body


def test_parse_simple_move() -> None:
    result = parse_email_body("e4")

    assert result.valid is True
    assert result.command == "move"
    assert result.value == "e4"
    assert result.delay_hours is None


def test_parse_move_with_delay() -> None:
    result = parse_email_body(
        """
        Nf3

        delay: 24h
        """
    )

    assert result.valid is True
    assert result.command == "move"
    assert result.value == "Nf3"
    assert result.delay_hours == 24


def test_ignore_quoted_previous_email() -> None:
    result = parse_email_body(
        """
        Nc6

        On Friday, Luis wrote:
        > Nf3
        > Previous game information
        """
    )

    assert result.value == "Nc6"


def test_ignore_email_signature() -> None:
    lines = extract_new_lines(
        """
        Bc4

        --
        Luis Fim
        Software Engineering Student
        """
    )

    assert lines == ["Bc4"]


def test_parse_resign_command() -> None:
    result = parse_email_body("RESIGN")

    assert result.valid is True
    assert result.command == "resign"
    assert result.value is None


def test_parse_show_board_command() -> None:
    result = parse_email_body("show board")

    assert result.valid is True
    assert result.command == "show_board"


def test_empty_email_is_rejected() -> None:
    result = parse_email_body(
        """
        > Previous message
        > e4
        """
    )

    assert result.valid is False
    assert result.command is None


def test_invalid_delay_is_ignored() -> None:
    result = parse_email_body(
        """
        e4
        delay: 1000h
        """
    )

    assert result.valid is True
    assert result.value == "e4"
    assert result.delay_hours is None
