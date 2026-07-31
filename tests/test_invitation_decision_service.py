from invitation_decision_service import process_invitation_reply
from invitation_service import process_new_game_email


def create_invitation(tmp_path, inviter_color: str = "white"):
    database_path = tmp_path / "test.db"

    invitation = process_new_game_email(
        sender_email="luis@example.com",
        subject="friend@example.com",
        body=f"color: {inviter_color}",
        db_path=database_path,
    )

    assert invitation.game is not None

    return database_path, invitation.game


def test_invited_opponent_can_accept(tmp_path) -> None:
    database_path, game = create_invitation(
        tmp_path,
        inviter_color="white",
    )

    result = process_invitation_reply(
        game_code=game.code,
        sender_email="friend@example.com",
        email_body="accept",
        db_path=database_path,
    )

    assert result.processed is True
    assert result.decision == "accept"
    assert result.game is not None
    assert result.game.status == "active"
    assert result.game.accepted_at is not None
    assert len(result.emails) == 2

    recipients = {
        email.recipient
        for email in result.emails
    }

    assert recipients == {
        "luis@example.com",
        "friend@example.com",
    }


def test_white_receives_first_move_email(tmp_path) -> None:
    database_path, game = create_invitation(
        tmp_path,
        inviter_color="black",
    )

    result = process_invitation_reply(
        game_code=game.code,
        sender_email="friend@example.com",
        email_body="accept",
        db_path=database_path,
    )

    white_email = next(
        email
        for email in result.emails
        if email.recipient == "friend@example.com"
    )

    assert "White to move" in white_email.subject
    assert "it is your turn" in white_email.body
    assert white_email.reply_address is not None


def test_inviter_cannot_accept_own_invitation(tmp_path) -> None:
    database_path, game = create_invitation(tmp_path)

    result = process_invitation_reply(
        game_code=game.code,
        sender_email="luis@example.com",
        email_body="accept",
        db_path=database_path,
    )

    assert result.processed is False
    assert result.decision is None
    assert result.game is not None
    assert result.game.status == "invited"
    assert "Only the invited opponent" in result.emails[0].body


def test_outsider_cannot_answer_invitation(tmp_path) -> None:
    database_path, game = create_invitation(tmp_path)

    result = process_invitation_reply(
        game_code=game.code,
        sender_email="stranger@example.com",
        email_body="accept",
        db_path=database_path,
    )

    assert result.processed is False
    assert "not part of this game" in result.emails[0].body


def test_invited_opponent_can_decline(tmp_path) -> None:
    database_path, game = create_invitation(tmp_path)

    result = process_invitation_reply(
        game_code=game.code,
        sender_email="friend@example.com",
        email_body="decline",
        db_path=database_path,
    )

    assert result.processed is True
    assert result.decision == "decline"
    assert result.game is not None
    assert result.game.status == "declined"
    assert len(result.emails) == 2

    inviter_email = next(
        email
        for email in result.emails
        if email.recipient == "luis@example.com"
    )

    assert "declined your chess invitation" in inviter_email.body


def test_unrecognized_reply_is_rejected(tmp_path) -> None:
    database_path, game = create_invitation(tmp_path)

    result = process_invitation_reply(
        game_code=game.code,
        sender_email="friend@example.com",
        email_body="maybe later",
        db_path=database_path,
    )

    assert result.processed is False
    assert result.game is not None
    assert result.game.status == "invited"
    assert "accept" in result.emails[0].body
    assert "decline" in result.emails[0].body


def test_invitation_cannot_be_accepted_twice(tmp_path) -> None:
    database_path, game = create_invitation(tmp_path)

    first_result = process_invitation_reply(
        game_code=game.code,
        sender_email="friend@example.com",
        email_body="accept",
        db_path=database_path,
    )

    assert first_result.processed is True

    second_result = process_invitation_reply(
        game_code=game.code,
        sender_email="friend@example.com",
        email_body="accept",
        db_path=database_path,
    )

    assert second_result.processed is False
    assert "no longer waiting" in second_result.emails[0].body
