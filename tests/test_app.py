from fastapi.testclient import TestClient

from app import app
from email_gateway import MAIN_EMAIL_ADDRESS


client = TestClient(app)


def configure_test_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "CHESSPOST_DATABASE",
        str(tmp_path / "test.db"),
    )
    monkeypatch.setenv(
        "CHESSPOST_ATTACHMENTS",
        str(tmp_path / "boards"),
    )


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_creates_invitation(monkeypatch, tmp_path) -> None:
    configure_test_paths(monkeypatch, tmp_path)

    response = client.post(
        "/webhooks/inbound-email",
        json={
            "sender_email": "luis@example.com",
            "recipient_email": MAIN_EMAIL_ADDRESS,
            "subject": "friend@example.com",
            "body": "color: white",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["route"] == "new_game"
    assert data["processed"] is True
    assert data["game_code"] is not None
    assert len(data["emails"]) == 1

    invitation = data["emails"][0]

    assert invitation["recipient"] == "friend@example.com"
    assert invitation["reply_address"].startswith("game-")
    assert "accept" in invitation["body"]


def test_webhook_rejects_incomplete_json() -> None:
    response = client.post(
        "/webhooks/inbound-email",
        json={
            "sender_email": "luis@example.com",
        },
    )

    assert response.status_code == 422


def test_resend_webhook_requires_secret(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "RESEND_WEBHOOK_SECRET",
        raising=False,
    )

    response = client.post(
        "/webhooks/resend",
        content=b"{}",
    )

    assert response.status_code == 503


def test_resend_webhook_processes_received_email(
    monkeypatch,
    tmp_path,
) -> None:
    import app as app_module
    from resend_inbound import ReceivedEmail

    configure_test_paths(monkeypatch, tmp_path)

    monkeypatch.setenv(
        "RESEND_WEBHOOK_SECRET",
        "whsec_test",
    )
    monkeypatch.setenv(
        "CHESSPOST_EMAIL_MODE",
        "console",
    )

    def fake_verify_resend_event(
        raw_payload,
        headers,
        webhook_secret,
    ):
        assert raw_payload
        assert webhook_secret == "whsec_test"

        return {
            "type": "email.received",
            "data": {
                "email_id": "email-123",
            },
        }

    def fake_fetch_received_email(
        email_id,
        fallback_message_id=None,
    ):
        assert email_id == "email-123"

        return ReceivedEmail(
            email_id=email_id,
            sender_email="luis@example.com",
            recipient_email=MAIN_EMAIL_ADDRESS,
            subject="friend@example.com",
            body="color: white",
        )

    monkeypatch.setattr(
        app_module,
        "verify_resend_event",
        fake_verify_resend_event,
    )
    monkeypatch.setattr(
        app_module,
        "fetch_received_email",
        fake_fetch_received_email,
    )

    response = client.post(
        "/webhooks/resend",
        content=b'{"type":"email.received"}',
        headers={
            "svix-id": "msg_test",
            "svix-timestamp": "1234567890",
            "svix-signature": "v1,test",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["received_email_id"] == "email-123"
    assert data["route"] == "new_game"
    assert data["processed"] is True
    assert data["emails"][0]["recipient"] == (
        "friend@example.com"
    )


def test_resend_webhook_ignores_other_events(
    monkeypatch,
) -> None:
    import app as app_module

    monkeypatch.setenv(
        "RESEND_WEBHOOK_SECRET",
        "whsec_test",
    )

    def fake_verify_resend_event(
        raw_payload,
        headers,
        webhook_secret,
    ):
        return {
            "type": "email.delivered",
            "data": {},
        }

    monkeypatch.setattr(
        app_module,
        "verify_resend_event",
        fake_verify_resend_event,
    )

    response = client.post(
        "/webhooks/resend",
        content=b'{"type":"email.delivered"}',
    )

    assert response.status_code == 200
    assert response.json() == {
        "ignored": True,
        "event_type": "email.delivered",
    }


def test_resend_webhook_saves_sender_thread(
    monkeypatch,
    tmp_path,
) -> None:
    import app as app_module
    from resend_inbound import ReceivedEmail
    from thread_store import get_thread_context

    configure_test_paths(monkeypatch, tmp_path)

    monkeypatch.setenv(
        "RESEND_WEBHOOK_SECRET",
        "whsec_test",
    )
    monkeypatch.setenv(
        "CHESSPOST_EMAIL_MODE",
        "console",
    )

    def fake_verify(
        raw_payload,
        headers,
        webhook_secret,
    ):
        return {
            "type": "email.received",
            "data": {
                "email_id": "email-thread-123",
                "message_id": "<start@example.com>",
            },
        }

    def fake_fetch(
        email_id,
        fallback_message_id=None,
    ):
        return ReceivedEmail(
            email_id=email_id,
            sender_email="luis@example.com",
            recipient_email=MAIN_EMAIL_ADDRESS,
            subject="friend@example.com",
            body="color: white",
            message_id="<start@example.com>",
            references=("<older@example.com>",),
        )

    monkeypatch.setattr(
        app_module,
        "verify_resend_event",
        fake_verify,
    )
    monkeypatch.setattr(
        app_module,
        "fetch_received_email",
        fake_fetch,
    )

    response = client.post(
        "/webhooks/resend",
        content=b'{"type":"email.received"}',
    )

    assert response.status_code == 200

    data = response.json()
    game_code = data["game_code"]

    context = get_thread_context(
        game_code,
        "luis@example.com",
        tmp_path / "test.db",
    )

    assert context is not None
    assert context.last_message_id == "<start@example.com>"
    assert context.references == (
        "<older@example.com>",
        "<start@example.com>",
    )


def test_apply_thread_headers_for_recipient(
    monkeypatch,
    tmp_path,
) -> None:
    import app as app_module
    from database import create_game
    from email_gateway import GatewayResult, OutgoingEmail
    from thread_store import save_thread_context

    database_path = tmp_path / "test.db"

    monkeypatch.setenv(
        "CHESSPOST_DATABASE",
        str(database_path),
    )

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    save_thread_context(
        game_code=game.code,
        player_email="black@example.com",
        message_id="<black-accept@example.com>",
        references="<invitation@example.com>",
        db_path=database_path,
    )

    result = GatewayResult(
        route="game_message",
        processed=True,
        game_code=game.code,
        emails=(
            OutgoingEmail(
                recipient="black@example.com",
                subject=f"[Chesspost {game.code[:8]}] e4",
                body="White played e4.",
                reply_address=(
                    f"game-{game.code}@chesspost.test"
                ),
                attachment_path=None,
                delay_hours=0,
            ),
        ),
    )

    threaded_result = app_module.apply_thread_headers(
        result
    )

    outgoing = threaded_result.emails[0]

    assert outgoing.subject.startswith("Re: ")
    assert outgoing.headers == {
        "In-Reply-To": "<black-accept@example.com>",
        "References": (
            "<invitation@example.com> "
            "<black-accept@example.com>"
        ),
    }


def test_duplicate_resend_email_is_processed_once(
    monkeypatch,
    tmp_path,
) -> None:
    import app as app_module
    from resend_inbound import ReceivedEmail

    configure_test_paths(monkeypatch, tmp_path)

    monkeypatch.setenv(
        "RESEND_WEBHOOK_SECRET",
        "whsec_test",
    )
    monkeypatch.setenv(
        "CHESSPOST_EMAIL_MODE",
        "console",
    )

    fetch_count = 0

    def fake_verify(
        raw_payload,
        headers,
        webhook_secret,
    ):
        return {
            "type": "email.received",
            "data": {
                "email_id": "duplicate-email-123",
                "message_id": "<duplicate@example.com>",
            },
        }

    def fake_fetch(
        email_id,
        fallback_message_id=None,
    ):
        nonlocal fetch_count
        fetch_count += 1

        return ReceivedEmail(
            email_id=email_id,
            sender_email="luis@example.com",
            recipient_email=MAIN_EMAIL_ADDRESS,
            subject="friend@example.com",
            body="color: white",
            message_id="<duplicate@example.com>",
        )

    monkeypatch.setattr(
        app_module,
        "verify_resend_event",
        fake_verify,
    )
    monkeypatch.setattr(
        app_module,
        "fetch_received_email",
        fake_fetch,
    )

    first_response = client.post(
        "/webhooks/resend",
        content=b'{"type":"email.received"}',
        headers={"svix-id": "event-first"},
    )

    second_response = client.post(
        "/webhooks/resend",
        content=b'{"type":"email.received"}',
        headers={"svix-id": "event-second"},
    )

    assert first_response.status_code == 200
    assert first_response.json()["processed"] is True

    assert second_response.status_code == 200
    assert second_response.json() == {
        "duplicate": True,
        "received_email_id": "duplicate-email-123",
    }

    assert fetch_count == 1
