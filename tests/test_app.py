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
