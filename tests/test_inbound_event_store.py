from inbound_event_store import (
    claim_inbound_email,
    get_inbound_email_record,
    mark_inbound_email_processed,
    release_inbound_email_claim,
)


def test_first_claim_is_accepted(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    claimed = claim_inbound_email(
        email_id="email-123",
        event_id="event-123",
        db_path=database_path,
    )

    assert claimed is True


def test_duplicate_claim_is_rejected(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    first = claim_inbound_email(
        email_id="email-123",
        event_id="event-first",
        db_path=database_path,
    )

    second = claim_inbound_email(
        email_id="email-123",
        event_id="event-second",
        db_path=database_path,
    )

    assert first is True
    assert second is False


def test_processed_email_is_recorded(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    claim_inbound_email(
        email_id="email-123",
        event_id="event-123",
        db_path=database_path,
    )

    mark_inbound_email_processed(
        "email-123",
        database_path,
    )

    record = get_inbound_email_record(
        "email-123",
        database_path,
    )

    assert record is not None
    assert record.status == "processed"
    assert record.processed_at is not None


def test_failed_claim_can_be_retried(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    claim_inbound_email(
        email_id="email-123",
        event_id="event-first",
        db_path=database_path,
    )

    release_inbound_email_claim(
        "email-123",
        database_path,
    )

    claimed_again = claim_inbound_email(
        email_id="email-123",
        event_id="event-second",
        db_path=database_path,
    )

    assert claimed_again is True


def test_processed_claim_is_not_released(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    claim_inbound_email(
        email_id="email-123",
        event_id="event-123",
        db_path=database_path,
    )

    mark_inbound_email_processed(
        "email-123",
        database_path,
    )

    release_inbound_email_claim(
        "email-123",
        database_path,
    )

    claimed_again = claim_inbound_email(
        email_id="email-123",
        event_id="event-second",
        db_path=database_path,
    )

    assert claimed_again is False
