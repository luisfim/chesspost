import resend

from resend_inbound import (
    fetch_received_email,
    get_received_email_id,
    html_to_text,
    normalize_email_address,
)


def test_extract_email_from_display_name() -> None:
    result = normalize_email_address(
        "Luis Fim <LUIS@EXAMPLE.COM>"
    )

    assert result == "luis@example.com"


def test_html_email_is_converted_to_text() -> None:
    result = html_to_text(
        """
        <html>
            <body>
                <p>Nf3</p>
                <p>delay: 24h</p>
                <script>ignored()</script>
            </body>
        </html>
        """
    )

    assert "Nf3" in result
    assert "delay: 24h" in result
    assert "ignored" not in result


def test_extract_email_id_from_received_event() -> None:
    email_id = get_received_email_id(
        {
            "type": "email.received",
            "data": {
                "email_id": "email-123",
            },
        }
    )

    assert email_id == "email-123"


def test_non_received_event_is_ignored() -> None:
    email_id = get_received_email_id(
        {
            "type": "email.delivered",
            "data": {
                "email_id": "email-123",
            },
        }
    )

    assert email_id is None


def test_fetch_plain_text_received_email(
    monkeypatch,
) -> None:
    def fake_get(*, email_id):
        assert email_id == "email-123"

        return {
            "id": email_id,
            "from": "Luis Fim <LUIS@EXAMPLE.COM>",
            "to": ["PLAY@CHESSPOST.TEST"],
            "subject": "friend@example.com",
            "text": "color: white",
            "html": None,
        }

    monkeypatch.setattr(
        resend.Emails.Receiving,
        "get",
        fake_get,
    )

    email = fetch_received_email(
        "email-123",
        api_key="re_test_key",
    )

    assert email.email_id == "email-123"
    assert email.sender_email == "luis@example.com"
    assert email.recipient_email == "play@chesspost.test"
    assert email.subject == "friend@example.com"
    assert email.body == "color: white"


def test_fetch_html_only_received_email(
    monkeypatch,
) -> None:
    def fake_get(*, email_id):
        return {
            "id": email_id,
            "from": "friend@example.com",
            "to": ["game-123@chesspost.test"],
            "subject": "Re: Chesspost",
            "text": None,
            "html": "<p>accept</p>",
        }

    monkeypatch.setattr(
        resend.Emails.Receiving,
        "get",
        fake_get,
    )

    email = fetch_received_email(
        "email-456",
        api_key="re_test_key",
    )

    assert email.body == "accept"
