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


def test_resign_finishes_game_and_emails_both_players(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"
    boards = tmp_path / "boards"

    invitation = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="black@example.com",
        body="color: white",
        db_path=database_path,
        attachment_directory=boards,
    )

    game_address = invitation.emails[0].reply_address
    assert game_address is not None

    process_incoming_email(
        sender_email="black@example.com",
        recipient_email=game_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    result = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=game_address,
        subject="Re: game",
        body="resign",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert result.route == "game_finished"
    assert result.processed is True
    assert len(result.emails) == 2

    recipients = {
        email.recipient
        for email in result.emails
    }

    assert recipients == {
        "white@example.com",
        "black@example.com",
    }

    for email in result.emails:
        assert "Resignation" in email.body
        assert "black@example.com wins" in email.body
        assert "rematch" in email.body
        assert email.attachment_path is not None


def test_checkmate_sends_final_report_to_both_players(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"
    boards = tmp_path / "boards"

    invitation = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="black@example.com",
        body="color: white",
        db_path=database_path,
        attachment_directory=boards,
    )

    game_address = invitation.emails[0].reply_address
    assert game_address is not None

    process_incoming_email(
        sender_email="black@example.com",
        recipient_email=game_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    sequence = [
        ("white@example.com", "f3"),
        ("black@example.com", "e5"),
        ("white@example.com", "g4"),
    ]

    for sender, move in sequence:
        result = process_incoming_email(
            sender_email=sender,
            recipient_email=game_address,
            subject="Re: game",
            body=move,
            db_path=database_path,
            attachment_directory=boards,
        )

        assert result.processed is True

    mate = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=game_address,
        subject="Re: game",
        body="Qh4#",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert mate.route == "game_finished"
    assert len(mate.emails) == 2

    for email in mate.emails:
        assert "Checkmate" in email.body
        assert "black@example.com wins" in email.body
        assert "Moves: 2" in email.body


def test_finished_game_can_create_rematch(
    tmp_path,
) -> None:
    from database import get_game

    database_path = tmp_path / "test.db"
    boards = tmp_path / "boards"

    invitation = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="black@example.com",
        body="""
        color: white
        delay: 24h
        """,
        db_path=database_path,
        attachment_directory=boards,
    )

    old_game_code = invitation.game_code
    game_address = invitation.emails[0].reply_address

    assert old_game_code is not None
    assert game_address is not None

    process_incoming_email(
        sender_email="black@example.com",
        recipient_email=game_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    process_incoming_email(
        sender_email="white@example.com",
        recipient_email=game_address,
        subject="Re: game",
        body="resign",
        db_path=database_path,
        attachment_directory=boards,
    )

    rematch = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=game_address,
        subject="Re: game",
        body="rematch",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert rematch.route == "rematch"
    assert rematch.processed is True
    assert rematch.game_code is not None
    assert rematch.game_code != old_game_code
    assert len(rematch.emails) == 1

    new_game = get_game(
        rematch.game_code,
        database_path,
    )

    assert new_game is not None
    assert new_game.status == "invited"

    # Colors reversed.
    assert new_game.white_email == "black@example.com"
    assert new_game.black_email == "white@example.com"

    # Same delivery setting.
    assert new_game.delivery_delay_hours == 24

    invitation_email = rematch.emails[0]

    assert invitation_email.recipient == "black@example.com"
    assert invitation_email.reply_address is not None
    assert rematch.game_code in invitation_email.reply_address
    assert "Colors have been reversed" in invitation_email.body


def test_active_game_cannot_request_rematch(
    tmp_path,
) -> None:
    database_path = tmp_path / "test.db"
    boards = tmp_path / "boards"

    invitation = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=MAIN_EMAIL_ADDRESS,
        subject="black@example.com",
        body="color: white",
        db_path=database_path,
        attachment_directory=boards,
    )

    game_address = invitation.emails[0].reply_address
    assert game_address is not None

    process_incoming_email(
        sender_email="black@example.com",
        recipient_email=game_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    result = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=game_address,
        subject="Re: game",
        body="rematch",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert result.processed is False
    assert result.route == "game_message"
    assert "only be requested after" in result.emails[0].body
