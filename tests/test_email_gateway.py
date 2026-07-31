from email_gateway import (
    MAIN_EMAIL_ADDRESS,
    process_incoming_email,
)


def test_main_address_creates_invitation(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="friend@example.com",
        body="color: white",
        db_path=database_path,
        attachment_directory=tmp_path / "boards",
    )

    assert result.route == "new_game"
    assert result.processed is True
    assert result.game_code is not None
    assert len(result.emails) == 1

    invitation = result.emails[0]

    assert invitation.recipient == "friend@example.com"
    assert invitation.reply_address is not None
    assert invitation.reply_address.startswith("game-")
    assert "accept" in invitation.body


def test_invited_player_can_accept_through_gateway(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    invitation_result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="friend@example.com",
        body="color: white",
        db_path=database_path,
        attachment_directory=tmp_path / "boards",
    )

    invitation_email = invitation_result.emails[0]

    assert invitation_email.reply_address is not None

    acceptance_result = process_incoming_email(
        sender_email="friend@example.com",
        recipient_email=invitation_email.reply_address,
        subject="Re: Chess invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=tmp_path / "boards",
    )

    assert acceptance_result.route == "invitation_reply"
    assert acceptance_result.processed is True
    assert len(acceptance_result.emails) == 2

    recipients = {
        email.recipient
        for email in acceptance_result.emails
    }

    assert recipients == {
        "luis@example.com",
        "friend@example.com",
    }


def test_game_can_continue_through_gateway(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    board_directory = tmp_path / "boards"

    invitation_result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="friend@example.com",
        body="color: white",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    game_address = invitation_result.emails[0].reply_address

    assert game_address is not None

    process_incoming_email(
        sender_email="friend@example.com",
        recipient_email=game_address,
        subject="Re: Chess invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    move_result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=game_address,
        subject="Re: Game started",
        body="e4",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    assert move_result.route == "game_message"
    assert move_result.processed is True
    assert len(move_result.emails) == 1

    move_email = move_result.emails[0]

    assert move_email.recipient == "friend@example.com"
    assert move_email.attachment_path is not None
    assert move_email.attachment_path.exists()
    assert "played e4" in move_email.body


def test_illegal_move_returns_to_sender(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    board_directory = tmp_path / "boards"

    invitation_result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="friend@example.com",
        body="color: white",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    game_address = invitation_result.emails[0].reply_address

    assert game_address is not None

    process_incoming_email(
        sender_email="friend@example.com",
        recipient_email=game_address,
        subject="Re: Invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    illegal_result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=game_address,
        subject="Re: Game",
        body="e5",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    assert illegal_result.route == "game_message"
    assert illegal_result.processed is False

    error_email = illegal_result.emails[0]

    assert error_email.recipient == "luis@example.com"
    assert error_email.attachment_path is None
    assert "did not receive this move" in error_email.body


def test_unknown_recipient_returns_instructions(tmp_path) -> None:
    result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email="wrong@chesspost.test",
        subject="Hello",
        body="e4",
        db_path=tmp_path / "test.db",
        attachment_directory=tmp_path / "boards",
    )

    assert result.route == "unknown"
    assert result.processed is False
    assert result.emails[0].recipient == "luis@example.com"
    assert MAIN_EMAIL_ADDRESS in result.emails[0].body
