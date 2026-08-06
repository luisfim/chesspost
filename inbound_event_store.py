from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from database import DATABASE_PATH, connect, init_database


@dataclass(frozen=True)
class InboundEmailRecord:
    email_id: str
    event_id: str | None
    status: str
    first_seen_at: str
    processed_at: str | None


def init_inbound_event_table(
    db_path: Path = DATABASE_PATH,
) -> None:
    """Create storage used to prevent duplicate inbound processing."""
    init_database(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inbound_email_events (
                email_id TEXT PRIMARY KEY,
                event_id TEXT,
                status TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                processed_at TEXT
            )
            """
        )


def claim_inbound_email(
    *,
    email_id: str,
    event_id: str | None,
    db_path: Path = DATABASE_PATH,
) -> bool:
    """
    Claim an inbound email for processing.

    Returns False when another request already claimed it.
    """
    email_id = email_id.strip()

    if not email_id:
        raise ValueError("Email ID cannot be empty.")

    normalized_event_id = (
        event_id.strip()
        if event_id and event_id.strip()
        else None
    )

    init_inbound_event_table(db_path)
    now = datetime.now(timezone.utc).isoformat()

    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO inbound_email_events (
                email_id,
                event_id,
                status,
                first_seen_at,
                processed_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                email_id,
                normalized_event_id,
                "processing",
                now,
                None,
            ),
        )

        return cursor.rowcount == 1


def mark_inbound_email_processed(
    email_id: str,
    db_path: Path = DATABASE_PATH,
) -> None:
    """Mark an inbound email as successfully processed."""
    init_inbound_event_table(db_path)
    now = datetime.now(timezone.utc).isoformat()

    with connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE inbound_email_events
            SET
                status = ?,
                processed_at = ?
            WHERE email_id = ?
            """,
            (
                "processed",
                now,
                email_id.strip(),
            ),
        )

        if cursor.rowcount != 1:
            raise ValueError("Inbound email claim was not found.")


def release_inbound_email_claim(
    email_id: str,
    db_path: Path = DATABASE_PATH,
) -> None:
    """
    Release an unfinished claim so a provider retry can try again.

    Successfully processed records are never removed.
    """
    init_inbound_event_table(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            DELETE FROM inbound_email_events
            WHERE email_id = ?
              AND status = 'processing'
            """,
            (email_id.strip(),),
        )


def get_inbound_email_record(
    email_id: str,
    db_path: Path = DATABASE_PATH,
) -> InboundEmailRecord | None:
    """Retrieve the stored processing state for an inbound email."""
    init_inbound_event_table(db_path)

    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                email_id,
                event_id,
                status,
                first_seen_at,
                processed_at
            FROM inbound_email_events
            WHERE email_id = ?
            """,
            (email_id.strip(),),
        ).fetchone()

    if row is None:
        return None

    return InboundEmailRecord(
        email_id=row["email_id"],
        event_id=row["event_id"],
        status=row["status"],
        first_seen_at=row["first_seen_at"],
        processed_at=row["processed_at"],
    )
