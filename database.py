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
    created_at: str
    updated_at: str


def connect(db_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    """Open a connection to the Chesspost database."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(db_path: Path = DATABASE_PATH) -> None:
    """Create the database tables if they do not exist."""
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def create_game(
    white_email: str,
    black_email: str,
    db_path: Path = DATABASE_PATH,
) -> Game:
    """Create and save a new chess game."""
    white_email = white_email.strip().lower()
    black_email = black_email.strip().lower()

    if not white_email or not black_email:
        raise ValueError("Both players must have an email address.")

    if white_email == black_email:
        raise ValueError("A player cannot play against the same email address.")

    init_database(db_path)

    code = secrets.token_hex(8)
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
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                white_email,
                black_email,
                new_game_fen(),
                "active",
                None,
                now,
                now,
            ),
        )

    game = get_game(code, db_path)

    if game is None:
        raise RuntimeError("The game could not be created.")

    return game


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
                created_at,
                updated_at
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
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
