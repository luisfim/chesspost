from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import secrets
import sqlite3

from chess_engine import new_game_fen


DATABASE_PATH = Path("chesspost.db")


@dataclass(frozen=True)
class Game:
    code: str
    white_email: str
    black_email: str
    fen: str
    status: str
    result: str | None
    invited_by_email: str | None
    delivery_delay_hours: int
    created_at: str
    updated_at: str
    accepted_at: str | None


def connect(db_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    """Open a connection to the Chesspost database."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(db_path: Path = DATABASE_PATH) -> None:
    """Create and update the Chesspost database tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                code TEXT PRIMARY KEY,
                white_email TEXT NOT NULL,
                black_email TEXT NOT NULL,
                fen TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                result TEXT,
                invited_by_email TEXT,
                delivery_delay_hours INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                accepted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_code TEXT NOT NULL,
                ply INTEGER NOT NULL,
                player_email TEXT NOT NULL,
                san TEXT NOT NULL,
                fen_before TEXT NOT NULL,
                fen_after TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (game_code) REFERENCES games(code)
            );
            """
        )

        # Update databases created during earlier development steps.
        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(games)"
            ).fetchall()
        }

        if "invited_by_email" not in existing_columns:
            connection.execute(
                "ALTER TABLE games ADD COLUMN invited_by_email TEXT"
            )

        if "delivery_delay_hours" not in existing_columns:
            connection.execute(
                """
                ALTER TABLE games
                ADD COLUMN delivery_delay_hours INTEGER NOT NULL DEFAULT 0
                """
            )

        if "accepted_at" not in existing_columns:
            connection.execute(
                "ALTER TABLE games ADD COLUMN accepted_at TEXT"
            )


def validate_players(
    first_email: str,
    second_email: str,
) -> tuple[str, str]:
    """Normalize and validate two player email addresses."""
    first_email = first_email.strip().lower()
    second_email = second_email.strip().lower()

    if not first_email or not second_email:
        raise ValueError("Both players must have an email address.")

    if first_email == second_email:
        raise ValueError(
            "A player cannot play against the same email address."
        )

    return first_email, second_email


def insert_game(
    *,
    code: str,
    white_email: str,
    black_email: str,
    status: str,
    invited_by_email: str | None,
    delivery_delay_hours: int,
    accepted_at: str | None,
    db_path: Path,
) -> Game:
    """Insert a game into the database."""
    init_database(db_path)
    now = datetime.now(timezone.utc).isoformat()

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO games (
                code,
                white_email,
                black_email,
                fen,
                status,
                result,
                invited_by_email,
                delivery_delay_hours,
                created_at,
                updated_at,
                accepted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                white_email,
                black_email,
                new_game_fen(),
                status,
                None,
                invited_by_email,
                delivery_delay_hours,
                now,
                now,
                accepted_at,
            ),
        )

    game = get_game(code, db_path)

    if game is None:
        raise RuntimeError("The game could not be created.")

    return game


def create_game(
    white_email: str,
    black_email: str,
    db_path: Path = DATABASE_PATH,
    *,
    delivery_delay_hours: int = 0,
) -> Game:
    """Create an immediately active chess game."""
    white_email, black_email = validate_players(
        white_email,
        black_email,
    )

    if delivery_delay_hours < 0 or delivery_delay_hours > 720:
        raise ValueError("Delivery delay must be between 0 and 720 hours.")

    now = datetime.now(timezone.utc).isoformat()

    return insert_game(
        code=secrets.token_hex(8),
        white_email=white_email,
        black_email=black_email,
        status="active",
        invited_by_email=None,
        delivery_delay_hours=delivery_delay_hours,
        accepted_at=now,
        db_path=db_path,
    )


def create_invited_game(
    inviter_email: str,
    opponent_email: str,
    requested_color: str,
    delivery_delay_hours: int,
    db_path: Path = DATABASE_PATH,
) -> Game:
    """Create a game that is waiting for the opponent's acceptance."""
    inviter_email, opponent_email = validate_players(
        inviter_email,
        opponent_email,
    )

    requested_color = requested_color.strip().lower()

    if requested_color not in {"white", "black", "random"}:
        raise ValueError(
            'Requested color must be "white", "black", or "random".'
        )

    if delivery_delay_hours < 0 or delivery_delay_hours > 720:
        raise ValueError("Delivery delay must be between 0 and 720 hours.")

    assigned_color = requested_color

    if assigned_color == "random":
        assigned_color = secrets.choice(["white", "black"])

    if assigned_color == "white":
        white_email = inviter_email
        black_email = opponent_email
    else:
        white_email = opponent_email
        black_email = inviter_email

    return insert_game(
        code=secrets.token_hex(8),
        white_email=white_email,
        black_email=black_email,
        status="invited",
        invited_by_email=inviter_email,
        delivery_delay_hours=delivery_delay_hours,
        accepted_at=None,
        db_path=db_path,
    )


def get_game(
    code: str,
    db_path: Path = DATABASE_PATH,
) -> Game | None:
    """Retrieve a game using its unique code."""
    init_database(db_path)

    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                code,
                white_email,
                black_email,
                fen,
                status,
                result,
                invited_by_email,
                delivery_delay_hours,
                created_at,
                updated_at,
                accepted_at
            FROM games
            WHERE code = ?
            """,
            (code,),
        ).fetchone()

    if row is None:
        return None

    return Game(
        code=row["code"],
        white_email=row["white_email"],
        black_email=row["black_email"],
        fen=row["fen"],
        status=row["status"],
        result=row["result"],
        invited_by_email=row["invited_by_email"],
        delivery_delay_hours=row["delivery_delay_hours"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        accepted_at=row["accepted_at"],
    )
