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

    def fake_fetch_received_email(email_id):
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
