import os
import time
from datetime import datetime, timezone
from pathlib import Path

from activity_log import init_activity_table
from database import DATABASE_PATH, connect, init_database
from inbound_event_store import init_inbound_event_table


PROCESS_STARTED_AT = datetime.now(timezone.utc)
PROCESS_STARTED_MONOTONIC = time.monotonic()


def format_uptime(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"

    if hours:
        return f"{hours:02d}h {minutes:02d}m"

    if minutes:
        return f"{minutes:02d}m {seconds:02d}s"

    return f"{seconds}s"


def get_system_health(
    db_path: Path = DATABASE_PATH,
) -> dict[str, object]:
    """Return safe operational health information."""
    database_status = "offline"
    database_error = None

    try:
        init_database(db_path)
        init_activity_table(db_path)
        init_inbound_event_table(db_path)

        with connect(db_path) as connection:
            connection.execute("SELECT 1").fetchone()

        database_status = "online"

    except Exception as error:
        database_error = type(error).__name__

    last_webhook = None
    last_email = None
    recent_problems: list[dict[str, object]] = []

    if database_status == "online":
        with connect(db_path) as connection:
            webhook_row = connection.execute(
                """
                SELECT
                    email_id,
                    status,
                    first_seen_at,
                    processed_at
                FROM inbound_email_events
                ORDER BY first_seen_at DESC
                LIMIT 1
                """
            ).fetchone()

            if webhook_row is not None:
                last_webhook = {
                    "email_id": webhook_row["email_id"],
                    "status": webhook_row["status"],
                    "time": (
                        webhook_row["processed_at"]
                        or webhook_row["first_seen_at"]
                    ),
                }

            email_row = connection.execute(
                """
                SELECT
                    event_type,
                    target_email,
                    detail,
                    created_at
                FROM activity_events
                WHERE event_type IN (
                    'email_sent',
                    'email_scheduled'
                )
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            if email_row is not None:
                last_email = dict(email_row)

            problem_rows = connection.execute(
                """
                SELECT
                    event_type,
                    game_code,
                    actor_email,
                    detail,
                    created_at
                FROM activity_events
                WHERE event_type IN (
                    'system_error',
                    'move_rejected',
                    'command_rejected',
                    'invitation_rejected',
                    'security_rejected'
                )
                ORDER BY id DESC
                LIMIT 15
                """
            ).fetchall()

            recent_problems = [
                dict(row)
                for row in problem_rows
            ]

    uptime_seconds = int(
        time.monotonic()
        - PROCESS_STARTED_MONOTONIC
    )

    resend_api_configured = bool(
        os.getenv(
            "RESEND_API_KEY",
            "",
        ).strip()
    )

    resend_webhook_configured = bool(
        os.getenv(
            "RESEND_WEBHOOK_SECRET",
            "",
        ).strip()
    )

    email_mode = os.getenv(
        "CHESSPOST_EMAIL_MODE",
        "console",
    ).strip().lower()

    return {
        "database": {
            "status": database_status,
            "error": database_error,
        },
        "resend": {
            # Only booleans are exposed.
            # Secrets are never returned.
            "api_configured": resend_api_configured,
            "webhook_configured": resend_webhook_configured,
            "status": (
                "configured"
                if (
                    resend_api_configured
                    and resend_webhook_configured
                )
                else "incomplete"
            ),
        },
        "email_mode": email_mode,
        "last_webhook": last_webhook,
        "last_email": last_email,
        "recent_problems": recent_problems,
        "uptime": {
            "seconds": uptime_seconds,
            "display": format_uptime(
                uptime_seconds
            ),
            "started_at": (
                PROCESS_STARTED_AT.isoformat()
            ),
        },
    }
