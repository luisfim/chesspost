from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from database import (
    DATABASE_PATH,
    Game,
    connect,
    get_game,
    init_database,
)


@dataclass(frozen=True)
class DrawOffer:
    game_code: str
    offered_by_email: str
    created_at: str


@dataclass(frozen=True)
class DrawActionResult:
    accepted: bool
    message: str
    game: Game
    offer: DrawOffer | None


def init_draw_table(
    db_path: Path = DATABASE_PATH,
) -> None:
    """Create storage for pending draw offers."""
    init_database(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS draw_offers (
                game_code TEXT PRIMARY KEY,
                offered_by_email TEXT NOT NULL,
                created_at TEXT NOT NULL,

                FOREIGN KEY (game_code)
                    REFERENCES games(code)
                    ON DELETE CASCADE
            )
            """
        )


def get_draw_offer(
    game_code: str,
    db_path: Path = DATABASE_PATH,
) -> DrawOffer | None:
    """Return the pending draw offer for a game."""
    init_draw_table(db_path)

    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                game_code,
                offered_by_email,
                created_at
            FROM draw_offers
            WHERE game_code = ?
            """,
            (game_code,),
        ).fetchone()

    if row is None:
        return None

    return DrawOffer(
        game_code=row["game_code"],
        offered_by_email=row["offered_by_email"],
        created_at=row["created_at"],
    )


def clear_draw_offer(
    game_code: str,
    db_path: Path = DATABASE_PATH,
) -> None:
    """Remove a pending draw offer."""
    init_draw_table(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            DELETE FROM draw_offers
            WHERE game_code = ?
            """,
            (game_code,),
        )


def offer_draw(
    game_code: str,
    sender_email: str,
    db_path: Path = DATABASE_PATH,
) -> DrawActionResult:
    """Create a draw offer from one player."""
    game = get_game(game_code, db_path)

    if game is None:
        raise ValueError("Game not found.")

    sender_email = sender_email.strip().lower()

    if sender_email not in {
        game.white_email,
        game.black_email,
    }:
        return DrawActionResult(
            accepted=False,
            message="This email address is not a player in this game.",
            game=game,
            offer=None,
        )

    if game.status != "active":
        return DrawActionResult(
            accepted=False,
            message="This game has already finished.",
            game=game,
            offer=None,
        )

    existing_offer = get_draw_offer(
        game_code,
        db_path,
    )

    if existing_offer is not None:
        if existing_offer.offered_by_email == sender_email:
            return DrawActionResult(
                accepted=False,
                message="You already have a pending draw offer.",
                game=game,
                offer=existing_offer,
            )

        return DrawActionResult(
            accepted=False,
            message=(
                "Your opponent already offered a draw. "
                "Reply with 'accept draw' or 'decline draw'."
            ),
            game=game,
            offer=existing_offer,
        )

    now = datetime.now(timezone.utc).isoformat()

    init_draw_table(db_path)

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO draw_offers (
                game_code,
                offered_by_email,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                game_code,
                sender_email,
                now,
            ),
        )

    offer = get_draw_offer(
        game_code,
        db_path,
    )

    if offer is None:
        raise RuntimeError("Draw offer could not be created.")

    return DrawActionResult(
        accepted=True,
        message="Draw offer created.",
        game=game,
        offer=offer,
    )


def decline_draw(
    game_code: str,
    sender_email: str,
    db_path: Path = DATABASE_PATH,
) -> DrawActionResult:
    """Decline the opponent's pending draw offer."""
    game = get_game(game_code, db_path)

    if game is None:
        raise ValueError("Game not found.")

    sender_email = sender_email.strip().lower()
    offer = get_draw_offer(game_code, db_path)

    if offer is None:
        return DrawActionResult(
            accepted=False,
            message="There is no pending draw offer.",
            game=game,
            offer=None,
        )

    if sender_email == offer.offered_by_email:
        return DrawActionResult(
            accepted=False,
            message="You cannot decline your own draw offer.",
            game=game,
            offer=offer,
        )

    if sender_email not in {
        game.white_email,
        game.black_email,
    }:
        return DrawActionResult(
            accepted=False,
            message="This email address is not a player in this game.",
            game=game,
            offer=offer,
        )

    clear_draw_offer(game_code, db_path)

    return DrawActionResult(
        accepted=True,
        message="Draw offer declined.",
        game=game,
        offer=None,
    )


def accept_draw(
    game_code: str,
    sender_email: str,
    db_path: Path = DATABASE_PATH,
) -> DrawActionResult:
    """Accept the opponent's draw offer and finish the game."""
    game = get_game(game_code, db_path)

    if game is None:
        raise ValueError("Game not found.")

    sender_email = sender_email.strip().lower()
    offer = get_draw_offer(game_code, db_path)

    if offer is None:
        return DrawActionResult(
            accepted=False,
            message="There is no pending draw offer.",
            game=game,
            offer=None,
        )

    if sender_email == offer.offered_by_email:
        return DrawActionResult(
            accepted=False,
            message="You cannot accept your own draw offer.",
            game=game,
            offer=offer,
        )

    if sender_email not in {
        game.white_email,
        game.black_email,
    }:
        return DrawActionResult(
            accepted=False,
            message="This email address is not a player in this game.",
            game=game,
            offer=offer,
        )

    now = datetime.now(timezone.utc).isoformat()

    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE games
            SET
                status = 'finished',
                result = '1/2-1/2',
                updated_at = ?
            WHERE code = ?
            """,
            (
                now,
                game_code,
            ),
        )

        connection.execute(
            """
            DELETE FROM draw_offers
            WHERE game_code = ?
            """,
            (game_code,),
        )

    updated_game = get_game(
        game_code,
        db_path,
    )

    if updated_game is None:
        raise RuntimeError("Finished game could not be loaded.")

    return DrawActionResult(
        accepted=True,
        message="Draw accepted.",
        game=updated_game,
        offer=None,
    )
