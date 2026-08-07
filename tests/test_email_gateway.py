from game_mailbox import (
    GAME_EMAIL_DOMAIN,
    game_email_address as secure_game_email_address,
    resolve_game_email_address,
)

from email_gateway import (
    MAIN_EMAIL_ADDRESS,
    process_incoming_email,
)



def player_game_address(
    existing_address: str,
    player_email: str,
    database_path,
) -> str:
    """Return the secure game address belonging to one player."""
    resolved = resolve_game_email_address(
        existing_address,
        database_path,
    )

    assert resolved is not None

    return secure_game_email_address(
        resolved.game.code,
        player_email,
        database_path,
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
        recipient_email=player_game_address(
            game_address,
            "friend@example.com",
            database_path,
        ),
        subject="Re: Chess invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    move_result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=player_game_address(
            game_address,
            "luis@example.com",
            database_path,
        ),
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
        recipient_email=player_game_address(
            game_address,
            "friend@example.com",
            database_path,
        ),
        subject="Re: Invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=board_directory,
    )

    illegal_result = process_incoming_email(
        sender_email="luis@example.com",
        recipient_email=player_game_address(
            game_address,
            "luis@example.com",
            database_path,
        ),
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    result = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
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
            recipient_email=player_game_address(
                game_address,
                sender,
                database_path,
            ),
            subject="Re: game",
            body=move,
            db_path=database_path,
            attachment_directory=boards,
        )

        assert result.processed is True

    mate = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="resign",
        db_path=database_path,
        attachment_directory=boards,
    )

    rematch = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    result = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="rematch",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert result.processed is False
    assert result.route == "game_message"
    assert "only be requested after" in result.emails[0].body


def test_draw_offer_can_be_accepted_through_email(
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    offer = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="offer draw",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert offer.route == "draw_offer"
    assert offer.processed is True
    assert offer.emails[0].recipient == "black@example.com"

    accepted = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: game",
        body="accept draw",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert accepted.route == "game_finished"
    assert accepted.processed is True
    assert len(accepted.emails) == 2

    for email in accepted.emails:
        assert "Draw agreed" in email.body
        assert "1/2-1/2" in email.body
        assert "rematch" in email.body


def test_move_implicitly_declines_draw_offer(
    tmp_path,
) -> None:
    from draw_service import get_draw_offer

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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="e4",
        db_path=database_path,
        attachment_directory=boards,
    )

    process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="offer draw",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert get_draw_offer(
        invitation.game_code,
        database_path,
    ) is not None

    black_move = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: game",
        body="e5",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert black_move.processed is True

    assert get_draw_offer(
        invitation.game_code,
        database_path,
    ) is None


def test_player_can_request_help_by_email(
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    response = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="help",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert response.route == "game_help"
    assert response.processed is True
    assert len(response.emails) == 1
    assert response.emails[0].recipient == "white@example.com"
    assert "show board" in response.emails[0].body


def test_player_can_request_current_board_by_email(
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    response = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="show board",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert response.route == "game_board"
    assert response.processed is True
    assert len(response.emails) == 1
    assert response.emails[0].recipient == "white@example.com"
    assert response.emails[0].attachment_path is not None


def test_player_can_request_move_history_by_email(
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
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    process_incoming_email(
        sender_email="white@example.com",
        recipient_email=player_game_address(
            game_address,
            "white@example.com",
            database_path,
        ),
        subject="Re: game",
        body="e4",
        db_path=database_path,
        attachment_directory=boards,
    )

    response = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=player_game_address(
            game_address,
            "black@example.com",
            database_path,
        ),
        subject="Re: game",
        body="show moves",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert response.route == "game_moves"
    assert response.processed is True
    assert len(response.emails) == 1
    assert response.emails[0].recipient == "black@example.com"
    assert "1. e4" in response.emails[0].body


def test_new_game_invitation_uses_secure_player_address(
    tmp_path,
) -> None:
    from game_mailbox import resolve_game_email_address

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

    address = invitation.emails[0].reply_address

    assert address is not None

    resolved = resolve_game_email_address(
        address,
        database_path,
    )

    assert resolved is not None
    assert resolved.secure is True
    assert resolved.player_email == "black@example.com"


def test_each_player_receives_own_secret_address_after_accept(
    tmp_path,
) -> None:
    from game_mailbox import resolve_game_email_address

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

    black_address = invitation.emails[0].reply_address
    assert black_address is not None

    accepted = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=black_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert len(accepted.emails) == 2

    addresses = {
        email.recipient: email.reply_address
        for email in accepted.emails
    }

    assert addresses["white@example.com"] is not None
    assert addresses["black@example.com"] is not None

    assert (
        addresses["white@example.com"]
        != addresses["black@example.com"]
    )

    for player_email, address in addresses.items():
        resolved = resolve_game_email_address(
            address,
            database_path,
        )

        assert resolved is not None
        assert resolved.secure is True
        assert resolved.player_email == player_email


def test_move_reply_address_belongs_to_opponent(
    tmp_path,
) -> None:
    from game_mailbox import resolve_game_email_address

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

    black_address = invitation.emails[0].reply_address
    assert black_address is not None

    accepted = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=black_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    white_start_email = next(
        email
        for email in accepted.emails
        if email.recipient == "white@example.com"
    )

    white_address = white_start_email.reply_address
    assert white_address is not None

    move = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=white_address,
        subject="Re: game",
        body="e4",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert move.processed is True
    assert len(move.emails) == 1

    opponent_email = move.emails[0]

    assert opponent_email.recipient == "black@example.com"
    assert opponent_email.reply_address is not None

    resolved = resolve_game_email_address(
        opponent_email.reply_address,
        database_path,
    )

    assert resolved is not None
    assert resolved.player_email == "black@example.com"


def test_player_cannot_use_opponents_secret_address(
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

    black_address = invitation.emails[0].reply_address
    assert black_address is not None

    # White somehow learns Black's secret address and attempts
    # to use it.
    rejected = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=black_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert rejected.processed is False
    assert rejected.route == "security_rejected"
    assert len(rejected.emails) == 1
    assert rejected.emails[0].recipient == "white@example.com"


def test_shared_address_is_disabled_for_new_secure_game(
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

    assert invitation.game_code is not None

    old_shared_address = (
        f"game-{invitation.game_code}"
        f"@{GAME_EMAIL_DOMAIN}"
    )

    result = process_incoming_email(
        sender_email="black@example.com",
        recipient_email=old_shared_address,
        subject="Re: invitation",
        body="accept",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert result.processed is False
    assert result.route == "security_rejected"


def test_legacy_game_address_still_works(
    tmp_path,
) -> None:
    from database import create_game

    database_path = tmp_path / "test.db"
    boards = tmp_path / "boards"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    legacy_address = (
        f"game-{game.code}"
        f"@{GAME_EMAIL_DOMAIN}"
    )

    result = process_incoming_email(
        sender_email="white@example.com",
        recipient_email=legacy_address,
        subject="Re: old game",
        body="e4",
        db_path=database_path,
        attachment_directory=boards,
    )

    assert result.processed is True
    assert result.emails[0].recipient == "black@example.com"

    # An old game should not suddenly change address halfway through.
    assert (
        result.emails[0].reply_address
        == legacy_address
    )
