from pathlib import Path

import resend

from email_gateway import OutgoingEmail
from outbound_mailer import (
    build_resend_params,
    create_html_body,
    send_outgoing_email,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def create_email(
    attachment_path: Path | None = None,
    delay_hours: int = 0,
) -> OutgoingEmail:
    return OutgoingEmail(
        recipient="friend@example.com",
        subject="[Chesspost] e4",
        body=(
            "Luis played e4.\n\n"
            "It is now your turn."
        ),
        reply_address="game-example@chesspost.test",
        attachment_path=attachment_path,
        delay_hours=delay_hours,
    )


def test_html_preserves_paragraphs() -> None:
    result = create_html_body(
        "First paragraph.\n\nSecond paragraph.",
        include_board=False,
    )

    assert "<p>First paragraph.</p>" in result
    assert "<p>Second paragraph.</p>" in result
    assert "cid:chess-board" not in result


def test_board_image_is_last_in_html() -> None:
    result = create_html_body(
        "It is your turn.",
        include_board=True,
    )

    assert "cid:chess-board" in result
    assert result.rstrip().endswith("</p>")


def test_build_resend_params_with_board(tmp_path) -> None:
    board_path = tmp_path / "board.png"
    board_path.write_bytes(PNG_SIGNATURE + b"test-image")

    email = create_email(attachment_path=board_path)

    params = build_resend_params(
        email=email,
        sender_address="Chesspost <play@example.com>",
    )

    assert params["to"] == ["friend@example.com"]
    assert params["reply_to"] == (
        "game-example@chesspost.test"
    )
    assert "attachments" in params

    attachments = params["attachments"]

    assert isinstance(attachments, list)
    assert attachments[0]["filename"] == (
        "chesspost-board.png"
    )
    assert attachments[0]["content_id"] == "chess-board"
    assert "cid:chess-board" in str(params["html"])


def test_delay_is_sent_to_resend() -> None:
    email = create_email(delay_hours=24)

    params = build_resend_params(
        email=email,
        sender_address="Chesspost <play@example.com>",
    )

    assert params["scheduled_at"] == "in 24 hours"


def test_console_mode_does_not_call_resend(
    monkeypatch,
    capsys,
) -> None:
    email = create_email()

    def fail_if_called(params):
        raise AssertionError("Resend should not be called")

    monkeypatch.setattr(
        resend.Emails,
        "send",
        fail_if_called,
    )

    result = send_outgoing_email(
        email,
        mode="console",
    )

    output = capsys.readouterr().out

    assert result.mode == "console"
    assert result.provider_id is None
    assert "CHESSPOST OUTGOING EMAIL" in output
    assert "friend@example.com" in output


def test_resend_mode_calls_provider(
    monkeypatch,
) -> None:
    email = create_email(delay_hours=24)
    captured: dict[str, object] = {}

    def fake_send(params):
        captured.update(params)
        return {"id": "email-test-123"}

    monkeypatch.setenv(
        "RESEND_API_KEY",
        "re_test_key",
    )
    monkeypatch.setenv(
        "CHESSPOST_FROM_EMAIL",
        "Chesspost <play@example.com>",
    )
    monkeypatch.setattr(
        resend.Emails,
        "send",
        fake_send,
    )

    result = send_outgoing_email(
        email,
        mode="resend",
    )

    assert result.mode == "resend"
    assert result.provider_id == "email-test-123"
    assert result.scheduled is True
    assert captured["scheduled_at"] == "in 24 hours"


def test_resend_params_include_thread_headers() -> None:
    email = OutgoingEmail(
        recipient="friend@example.com",
        subject="Re: [Chesspost] Game",
        body="It is your turn.",
        reply_address="game-example@chesspost.test",
        attachment_path=None,
        delay_hours=0,
        headers={
            "In-Reply-To": "<friend-move@example.com>",
            "References": (
                "<invitation@example.com> "
                "<friend-move@example.com>"
            ),
        },
    )

    params = build_resend_params(
        email=email,
        sender_address="Chesspost <play@example.com>",
    )

    assert params["headers"] == {
        "In-Reply-To": "<friend-move@example.com>",
        "References": (
            "<invitation@example.com> "
            "<friend-move@example.com>"
        ),
    }


def test_hybrid_mode_sends_allowed_recipient(
    monkeypatch,
) -> None:
    email = create_email()
    captured: dict[str, object] = {}

    def fake_send(params):
        captured.update(params)
        return {"id": "email-hybrid-123"}

    monkeypatch.setenv(
        "RESEND_API_KEY",
        "re_test_key",
    )
    monkeypatch.setenv(
        "CHESSPOST_FROM_EMAIL",
        "Chesspost <play@example.com>",
    )
    monkeypatch.setenv(
        "CHESSPOST_REAL_RECIPIENTS",
        "friend@example.com",
    )
    monkeypatch.setattr(
        resend.Emails,
        "send",
        fake_send,
    )

    result = send_outgoing_email(
        email,
        mode="hybrid",
    )

    assert result.mode == "resend"
    assert result.provider_id == "email-hybrid-123"
    assert captured["to"] == ["friend@example.com"]


def test_hybrid_mode_prints_unlisted_recipient(
    monkeypatch,
    capsys,
) -> None:
    email = create_email()

    def fail_if_called(params):
        raise AssertionError(
            "Resend should not receive this email."
        )

    monkeypatch.setenv(
        "CHESSPOST_REAL_RECIPIENTS",
        "another@example.com",
    )
    monkeypatch.setattr(
        resend.Emails,
        "send",
        fail_if_called,
    )

    result = send_outgoing_email(
        email,
        mode="hybrid",
    )

    output = capsys.readouterr().out

    assert result.mode == "console"
    assert result.provider_id is None
    assert "CHESSPOST OUTGOING EMAIL" in output


def test_real_recipient_allowlist_is_normalized() -> None:
    from outbound_mailer import parse_real_recipients

    result = parse_real_recipients(
        " LUIS@example.com, friend@example.com "
    )

    assert result == {
        "luis@example.com",
        "friend@example.com",
    }
