from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from database import (
    DATABASE_PATH,
    connect,
    get_game,
    init_database,
)


@dataclass(frozen=True)
class ThreadContext:
    game_code: str
    player_email: str
    last_message_id: str
    references: tuple[str, ...]
    subject: str
    updated_at: str


def init_thread_table(
    db_path: Path = DATABASE_PATH,
) -> None:
    """Create and migrate storage for each player's email thread."""
    init_database(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS email_threads (
                game_code TEXT NOT NULL,
                player_email TEXT NOT NULL,
                last_message_id TEXT NOT NULL,
                references_text TEXT NOT NULL,
                subject_text TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,

                PRIMARY KEY (game_code, player_email),

                FOREIGN KEY (game_code)
                    REFERENCES games(code)
                    ON DELETE CASCADE
            )
            """
        )

        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(email_threads)"
            ).fetchall()
        }

        if "subject_text" not in existing_columns:
            connection.execute(
                """
                ALTER TABLE email_threads
                ADD COLUMN subject_text TEXT NOT NULL DEFAULT ''
                """
            )


def normalize_references(
    references: str | list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Normalize and deduplicate RFC email message IDs."""
    if references is None:
        return ()

    if isinstance(references, str):
        message_ids = re.findall(r"<[^<>]+>", references)

        if not message_ids:
            message_ids = references.split()
    else:
        message_ids = []

        for value in references:
            message_ids.extend(
                re.findall(r"<[^<>]+>", value)
                or value.split()
            )

    normalized: list[str] = []

    for message_id in message_ids:
        message_id = message_id.strip()

        if message_id and message_id not in normalized:
            normalized.append(message_id)

    return tuple(normalized)


def normalize_thread_subject(subject: str | None) -> str:
    """Remove repeated reply/forward prefixes from an email subject."""
    normalized = (subject or "").strip()

    while True:
        updated = re.sub(
            r"^(?:re|fw|fwd)\s*:\s*",
            "",
            normalized,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

        if updated == normalized:
            break

        normalized = updated

    return normalized


def get_thread_context(
    game_code: str,
    player_email: str,
    db_path: Path = DATABASE_PATH,
) -> ThreadContext | None:
    """Retrieve the latest thread state for one player."""
    init_thread_table(db_path)
    player_email = player_email.strip().lower()

    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                game_code,
                player_email,
                last_message_id,
                references_text,
                subject_text,
                updated_at
            FROM email_threads
            WHERE game_code = ?
              AND player_email = ?
            """,
            (
                game_code,
                player_email,
            ),
        ).fetchone()

    if row is None:
        return None

    return ThreadContext(
        game_code=row["game_code"],
        player_email=row["player_email"],
        last_message_id=row["last_message_id"],
        references=normalize_references(
            row["references_text"]
        ),
        subject=row["subject_text"],
        updated_at=row["updated_at"],
    )


def save_thread_context(
    *,
    game_code: str,
    player_email: str,
    message_id: str,
    references: str | list[str] | tuple[str, ...] | None = None,
    subject: str = "",
    db_path: Path = DATABASE_PATH,
) -> ThreadContext:
    """Save the most recent inbound message from one player."""
    game = get_game(game_code, db_path)

    if game is None:
        raise ValueError("Game not found.")

    player_email = player_email.strip().lower()

    if player_email not in {
        game.white_email,
        game.black_email,
    }:
        raise ValueError(
            "This email address is not a player in the game."
        )

    message_id = message_id.strip()

    if not message_id:
        raise ValueError("Message ID cannot be empty.")

    reference_chain = list(
        normalize_references(references)
    )

    if message_id not in reference_chain:
        reference_chain.append(message_id)

    normalized_subject = normalize_thread_subject(subject)
    now = datetime.now(timezone.utc).isoformat()

    init_thread_table(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO email_threads (
                game_code,
                player_email,
                last_message_id,
                references_text,
                subject_text,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(game_code, player_email)
            DO UPDATE SET
                last_message_id = excluded.last_message_id,
                references_text = excluded.references_text,
                subject_text = CASE
                    WHEN excluded.subject_text <> ''
                    THEN excluded.subject_text
                    ELSE email_threads.subject_text
                END,
                updated_at = excluded.updated_at
            """,
            (
                game_code,
                player_email,
                message_id,
                " ".join(reference_chain),
                normalized_subject,
                now,
            ),
        )

    context = get_thread_context(
        game_code,
        player_email,
        db_path,
    )

    if context is None:
        raise RuntimeError(
            "The email thread context could not be saved."
        )

    return context


def build_reply_headers(
    game_code: str,
    player_email: str,
    db_path: Path = DATABASE_PATH,
) -> dict[str, str]:
    """Build headers that continue this player's game thread."""
    context = get_thread_context(
        game_code,
        player_email,
        db_path,
    )

    if context is None:
        return {}

    return {
        "In-Reply-To": context.last_message_id,
        "References": " ".join(context.references),
    }


def build_reply_subject(
    game_code: str,
    player_email: str,
    db_path: Path = DATABASE_PATH,
) -> str | None:
    """Return the reply subject used by this player's thread."""
    context = get_thread_context(
        game_code,
        player_email,
        db_path,
    )

    if context is None or not context.subject:
        return None

    return f"Re: {context.subject}"
