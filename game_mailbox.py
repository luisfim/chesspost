from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import secrets

from database import (
    DATABASE_PATH,
    Game,
    connect,
    get_game,
    init_database,
)


GAME_EMAIL_DOMAIN = os.getenv(
    "CHESSPOST_EMAIL_DOMAIN",
    "chesspost.test",
).strip().lower()

TOKEN_BYTES = 12
TOKEN_HEX_LENGTH = TOKEN_BYTES * 2


@dataclass(frozen=True)
class GameMailbox:
    game_code: str
    player_email: str
    token: str
    created_at: str


@dataclass(frozen=True)
class ResolvedGameAddress:
    game: Game
    player_email: str | None
    secure: bool


def init_game_mailbox_table(
    db_path: Path = DATABASE_PATH,
) -> None:
    """Create persistent per-player game email aliases."""
    init_database(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS game_mailboxes (
                game_code TEXT NOT NULL,
                player_email TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,

                PRIMARY KEY (
                    game_code,
                    player_email
                ),

                FOREIGN KEY (game_code)
                    REFERENCES games(code)
                    ON DELETE CASCADE
            )
            """
        )


def get_game_mailbox(
    game_code: str,
    player_email: str,
    db_path: Path = DATABASE_PATH,
) -> GameMailbox | None:
    init_game_mailbox_table(db_path)

    game_code = game_code.strip().lower()
    player_email = player_email.strip().lower()

    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                game_code,
                player_email,
                token,
                created_at
            FROM game_mailboxes
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

    return GameMailbox(
        game_code=row["game_code"],
        player_email=row["player_email"],
        token=row["token"],
        created_at=row["created_at"],
    )


def game_has_secure_mailboxes(
    game_code: str,
    db_path: Path = DATABASE_PATH,
) -> bool:
    init_game_mailbox_table(db_path)

    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM game_mailboxes
            WHERE game_code = ?
            LIMIT 1
            """,
            (game_code.strip().lower(),),
        ).fetchone()

    return row is not None


def _create_mailbox(
    game_code: str,
    player_email: str,
    db_path: Path,
) -> GameMailbox:
    """
    Create one mailbox.

    A token collision is extraordinarily unlikely, but retry safely
    rather than relying on probability alone.
    """
    now = datetime.now(timezone.utc).isoformat()

    for _ in range(10):
        token = secrets.token_hex(
            TOKEN_BYTES
        )

        try:
            with connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO game_mailboxes (
                        game_code,
                        player_email,
                        token,
                        created_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        game_code,
                        player_email,
                        token,
                        now,
                    ),
                )

            mailbox = get_game_mailbox(
                game_code,
                player_email,
                db_path,
            )

            if mailbox is None:
                raise RuntimeError(
                    "Mailbox was created but could not be loaded."
                )

            return mailbox

        except Exception as error:
            existing = get_game_mailbox(
                game_code,
                player_email,
                db_path,
            )

            if existing is not None:
                return existing

            # UNIQUE token collision: try another random token.
            if "UNIQUE" in str(error).upper():
                continue

            raise

    raise RuntimeError(
        "Could not generate a unique game mailbox token."
    )


def ensure_game_mailboxes(
    game: Game,
    db_path: Path = DATABASE_PATH,
) -> tuple[GameMailbox, GameMailbox]:
    """Ensure White and Black each have their own secret address."""
    init_game_mailbox_table(db_path)

    mailboxes: list[GameMailbox] = []

    for player_email in (
        game.white_email,
        game.black_email,
    ):
        mailbox = get_game_mailbox(
            game.code,
            player_email,
            db_path,
        )

        if mailbox is None:
            mailbox = _create_mailbox(
                game.code,
                player_email,
                db_path,
            )

        mailboxes.append(mailbox)

    return (
        mailboxes[0],
        mailboxes[1],
    )


def game_email_address(
    game_code: str,
    player_email: str,
    db_path: Path = DATABASE_PATH,
) -> str:
    """
    Return the secret game address belonging to one player.

    The address remains stable for the entire game.
    """
    game = get_game(
        game_code,
        db_path,
    )

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

    ensure_game_mailboxes(
        game,
        db_path,
    )

    mailbox = get_game_mailbox(
        game.code,
        player_email,
        db_path,
    )

    if mailbox is None:
        raise RuntimeError(
            "Game mailbox could not be loaded."
        )

    return (
        f"game-{game.code}-{mailbox.token}"
        f"@{GAME_EMAIL_DOMAIN}"
    )


def _secure_pattern() -> re.Pattern[str]:
    return re.compile(
        (
            r"^game-"
            r"([a-f0-9]{16})"
            r"-"
            rf"([a-f0-9]{{{TOKEN_HEX_LENGTH}}})"
            r"@"
            + re.escape(GAME_EMAIL_DOMAIN)
            + r"$"
        ),
        re.IGNORECASE,
    )


def _legacy_pattern() -> re.Pattern[str]:
    return re.compile(
        (
            r"^game-"
            r"([a-f0-9]{16})"
            r"@"
            + re.escape(GAME_EMAIL_DOMAIN)
            + r"$"
        ),
        re.IGNORECASE,
    )


def resolve_game_email_address(
    recipient_email: str,
    db_path: Path = DATABASE_PATH,
) -> ResolvedGameAddress | None:
    """
    Resolve a game address.

    Secure addresses identify both the game and the player.

    Legacy addresses remain usable only for old games that do not
    already have secure mailboxes. This lets existing email threads
    continue working while preventing new games from falling back to
    the old shared address.
    """
    recipient_email = (
        recipient_email
        .strip()
        .lower()
    )

    secure_match = _secure_pattern().fullmatch(
        recipient_email
    )

    if secure_match:
        game_code = secure_match.group(1).lower()
        token = secure_match.group(2).lower()

        init_game_mailbox_table(db_path)

        with connect(db_path) as connection:
            row = connection.execute(
                """
                SELECT player_email
                FROM game_mailboxes
                WHERE game_code = ?
                  AND token = ?
                """,
                (
                    game_code,
                    token,
                ),
            ).fetchone()

        if row is None:
            return None

        game = get_game(
            game_code,
            db_path,
        )

        if game is None:
            return None

        return ResolvedGameAddress(
            game=game,
            player_email=row["player_email"],
            secure=True,
        )

    legacy_match = _legacy_pattern().fullmatch(
        recipient_email
    )

    if legacy_match:
        game_code = legacy_match.group(1).lower()

        game = get_game(
            game_code,
            db_path,
        )

        if game is None:
            return None

        # Once a game has secure aliases, its old shared alias
        # must no longer be accepted.
        if game_has_secure_mailboxes(
            game_code,
            db_path,
        ):
            return None

        return ResolvedGameAddress(
            game=game,
            player_email=None,
            secure=False,
        )

    return None
