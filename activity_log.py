from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from database import DATABASE_PATH, connect, init_database


@dataclass(frozen=True)
class ActivityEvent:
    id: int
    event_type: str
    game_code: str | None
    actor_email: str | None
    target_email: str | None
    detail: str | None
    created_at: str


def init_activity_table(
    db_path: Path = DATABASE_PATH,
) -> None:
    init_database(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                game_code TEXT,
                actor_email TEXT,
                target_email TEXT,
                detail TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_activity_events_created_at
            ON activity_events(created_at)
            """
        )


def log_activity(
    event_type: str,
    *,
    game_code: str | None = None,
    actor_email: str | None = None,
    target_email: str | None = None,
    detail: str | None = None,
    db_path: Path = DATABASE_PATH,
) -> None:
    """Store one safe operational event."""
    init_activity_table(db_path)

    now = datetime.now(timezone.utc).isoformat()

    normalized_detail = None

    if detail:
        normalized_detail = detail.strip()[:500]

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO activity_events (
                event_type,
                game_code,
                actor_email,
                target_email,
                detail,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_type.strip().lower(),
                game_code,
                actor_email,
                target_email,
                normalized_detail,
                now,
            ),
        )


def get_recent_activity(
    limit: int = 100,
    db_path: Path = DATABASE_PATH,
) -> tuple[ActivityEvent, ...]:
    init_activity_table(db_path)

    limit = max(1, min(limit, 500))

    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                event_type,
                game_code,
                actor_email,
                target_email,
                detail,
                created_at
            FROM activity_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return tuple(
        ActivityEvent(
            id=row["id"],
            event_type=row["event_type"],
            game_code=row["game_code"],
            actor_email=row["actor_email"],
            target_email=row["target_email"],
            detail=row["detail"],
            created_at=row["created_at"],
        )
        for row in rows
    )
