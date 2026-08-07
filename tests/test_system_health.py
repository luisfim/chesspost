from activity_log import log_activity
from inbound_event_store import (
    claim_inbound_email,
    mark_inbound_email_processed,
)
from system_health import (
    format_uptime,
    get_system_health,
)


def test_format_uptime() -> None:
    assert format_uptime(5) == "5s"
    assert format_uptime(65) == "01m 05s"
    assert format_uptime(3661) == "01h 01m"


def test_database_health_is_online(
    tmp_path,
) -> None:
    database_path = tmp_path / "health.db"

    health = get_system_health(
        database_path,
    )

    assert health["database"]["status"] == "online"


def test_resend_configuration_is_reported_without_secret(
    monkeypatch,
    tmp_path,
) -> None:
    database_path = tmp_path / "health.db"

    monkeypatch.setenv(
        "RESEND_API_KEY",
        "secret-api-key",
    )

    monkeypatch.setenv(
        "RESEND_WEBHOOK_SECRET",
        "secret-webhook-key",
    )

    health = get_system_health(
        database_path,
    )

    assert health["resend"]["status"] == "configured"

    serialized = str(health)

    assert "secret-api-key" not in serialized
    assert "secret-webhook-key" not in serialized


def test_last_webhook_is_reported(
    tmp_path,
) -> None:
    database_path = tmp_path / "health.db"

    claim_inbound_email(
        email_id="email-123",
        event_id="event-123",
        db_path=database_path,
    )

    mark_inbound_email_processed(
        "email-123",
        database_path,
    )

    health = get_system_health(
        database_path,
    )

    assert health["last_webhook"] is not None
    assert (
        health["last_webhook"]["email_id"]
        == "email-123"
    )


def test_recent_problem_is_reported(
    tmp_path,
) -> None:
    database_path = tmp_path / "health.db"

    log_activity(
        "system_error",
        detail="RuntimeError: inbound processing failed",
        db_path=database_path,
    )

    health = get_system_health(
        database_path,
    )

    assert len(
        health["recent_problems"]
    ) == 1

    assert (
        health["recent_problems"][0]["event_type"]
        == "system_error"
    )
