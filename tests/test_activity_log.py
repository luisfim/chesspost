from activity_log import (
    get_recent_activity,
    log_activity,
)


def test_activity_can_be_recorded(tmp_path) -> None:
    database_path = tmp_path / "activity.db"

    log_activity(
        "move_accepted",
        game_code="abc123",
        actor_email="white@example.com",
        target_email="black@example.com",
        detail="e4",
        db_path=database_path,
    )

    events = get_recent_activity(
        db_path=database_path,
    )

    assert len(events) == 1

    event = events[0]

    assert event.event_type == "move_accepted"
    assert event.game_code == "abc123"
    assert event.actor_email == "white@example.com"
    assert event.target_email == "black@example.com"
    assert event.detail == "e4"


def test_newest_activity_appears_first(tmp_path) -> None:
    database_path = tmp_path / "activity.db"

    log_activity(
        "first",
        db_path=database_path,
    )

    log_activity(
        "second",
        db_path=database_path,
    )

    events = get_recent_activity(
        db_path=database_path,
    )

    assert events[0].event_type == "second"
    assert events[1].event_type == "first"
