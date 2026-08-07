import os
import secrets
from pathlib import Path

import chess
import chess.svg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from database import connect, get_game, init_database
from inbound_event_store import init_inbound_event_table
from activity_log import (
    get_recent_activity,
    init_activity_table,
)


router = APIRouter()
security = HTTPBasic()


def database_path() -> Path:
    return Path(
        os.getenv(
            "CHESSPOST_DATABASE",
            "chesspost.db",
        )
    )


def require_admin(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    """Protect the private Chesspost dashboard."""
    expected_user = os.getenv("CHESSPOST_ADMIN_USER")
    expected_password = os.getenv("CHESSPOST_ADMIN_PASSWORD")

    if not expected_user or not expected_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin credentials are not configured.",
        )

    username_ok = secrets.compare_digest(
        credentials.username,
        expected_user,
    )

    password_ok = secrets.compare_digest(
        credentials.password,
        expected_password,
    )

    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={
                "WWW-Authenticate": "Basic",
            },
        )

    return credentials.username


def get_admin_snapshot() -> dict[str, object]:
    """Return a current snapshot of Chesspost activity."""
    db_path = database_path()

    init_database(db_path)
    init_inbound_event_table(db_path)
    init_activity_table(db_path)

    with connect(db_path) as connection:
        status_rows = connection.execute(
            """
            SELECT
                status,
                COUNT(*) AS total
            FROM games
            GROUP BY status
            """
        ).fetchall()

        games = connection.execute(
            """
            SELECT
                g.code,
                g.white_email,
                g.black_email,
                g.status,
                g.result,
                g.delivery_delay_hours,
                g.created_at,
                g.updated_at,
                (
                    SELECT COUNT(*)
                    FROM moves m
                    WHERE m.game_code = g.code
                ) AS plies
            FROM games g
            ORDER BY g.updated_at DESC
            LIMIT 50
            """
        ).fetchall()

        moves = connection.execute(
            """
            SELECT
                game_code,
                ply,
                player_email,
                san,
                created_at
            FROM moves
            ORDER BY id DESC
            LIMIT 40
            """
        ).fetchall()

        inbound_events = connection.execute(
            """
            SELECT
                email_id,
                event_id,
                status,
                first_seen_at,
                processed_at
            FROM inbound_email_events
            ORDER BY first_seen_at DESC
            LIMIT 40
            """
        ).fetchall()

    statuses = {
        row["status"]: row["total"]
        for row in status_rows
    }

    return {
        "status": "online",
        "counts": {
            "active": statuses.get("active", 0),
            "invited": statuses.get("invited", 0),
            "finished": statuses.get("finished", 0),
            "declined": statuses.get("declined", 0),
            "total": sum(statuses.values()),
        },
        "games": [
            dict(row)
            for row in games
        ],
        "moves": [
            dict(row)
            for row in moves
        ],
        "inbound_events": [
            dict(row)
            for row in inbound_events
        ],
        "activity_events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "game_code": event.game_code,
                "actor_email": event.actor_email,
                "target_email": event.target_email,
                "detail": event.detail,
                "created_at": event.created_at,
            }
            for event in get_recent_activity(
                100,
                db_path,
            )
        ],
    }


def get_game_snapshot(
    game_code: str,
) -> dict[str, object]:
    """Return detailed information about one game."""
    db_path = database_path()
    game_code = game_code.strip().lower()

    init_database(db_path)
    init_activity_table(db_path)

    game = get_game(
        game_code,
        db_path,
    )

    if game is None:
        raise HTTPException(
            status_code=404,
            detail="Game not found.",
        )

    board = chess.Board(game.fen)

    turn_email = None

    if game.status == "active":
        turn_email = (
            game.white_email
            if board.turn == chess.WHITE
            else game.black_email
        )

    with connect(db_path) as connection:
        moves = connection.execute(
            """
            SELECT
                ply,
                player_email,
                san,
                fen_before,
                fen_after,
                created_at
            FROM moves
            WHERE game_code = ?
            ORDER BY ply ASC
            """,
            (game.code,),
        ).fetchall()

        activity = connection.execute(
            """
            SELECT
                id,
                event_type,
                actor_email,
                target_email,
                detail,
                created_at
            FROM activity_events
            WHERE game_code = ?
            ORDER BY id DESC
            LIMIT 200
            """,
            (game.code,),
        ).fetchall()

    return {
        "game": {
            "code": game.code,
            "white_email": game.white_email,
            "black_email": game.black_email,
            "status": game.status,
            "result": game.result,
            "delivery_delay_hours": (
                game.delivery_delay_hours
            ),
            "created_at": game.created_at,
            "updated_at": game.updated_at,
            "accepted_at": game.accepted_at,
            "turn_email": turn_email,
            "in_check": board.is_check(),
            "fullmove_number": board.fullmove_number,
        },
        "moves": [
            dict(row)
            for row in moves
        ],
        "activity": [
            dict(row)
            for row in activity
        ],
    }


def get_game_board_svg(
    game_code: str,
) -> str:
    """Render the current position for the admin dashboard."""
    game = get_game(
        game_code.strip().lower(),
        database_path(),
    )

    if game is None:
        raise HTTPException(
            status_code=404,
            detail="Game not found.",
        )

    board = chess.Board(game.fen)

    return chess.svg.board(
        board=board,
        orientation=chess.WHITE,
        size=700,
        coordinates=True,
    )



ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Chesspost Control Room</title>

<style>
    :root {
        color-scheme: dark;
        --bg: #050805;
        --panel: #091009;
        --line: #183218;
        --green: #59ff72;
        --dim: #72a278;
        --white: #dfffe3;
        --red: #ff6464;
    }

    * {
        box-sizing: border-box;
    }

    body {
        margin: 0;
        background: var(--bg);
        color: var(--green);
        font-family:
            "Courier New",
            Courier,
            monospace;
        font-size: 14px;
    }

    main {
        width: min(1500px, calc(100% - 30px));
        margin: 25px auto 60px;
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 20px;
        margin-bottom: 25px;
    }

    h1 {
        margin: 0;
        font-size: clamp(1.4rem, 4vw, 2.2rem);
        letter-spacing: 0.08em;
    }

    .sub {
        margin-top: 8px;
        color: var(--dim);
    }

    .live {
        border: 1px solid var(--green);
        padding: 7px 10px;
        white-space: nowrap;
    }

    .blink {
        animation: blink 1.2s step-end infinite;
    }

    @keyframes blink {
        50% {
            opacity: 0;
        }
    }

    .stats {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 10px;
        margin-bottom: 20px;
    }

    .stat {
        min-height: 90px;
        padding: 15px;
        border: 1px solid var(--line);
        background: var(--panel);
    }

    .stat .label {
        color: var(--dim);
        font-size: 0.75rem;
    }

    .stat .value {
        margin-top: 8px;
        font-size: 1.8rem;
        color: var(--white);
    }

    section {
        margin-top: 20px;
        border: 1px solid var(--line);
        background: var(--panel);
    }

    section h2 {
        margin: 0;
        padding: 10px 12px;
        border-bottom: 1px solid var(--line);
        font-size: 0.85rem;
        letter-spacing: 0.12em;
    }

    .scroll {
        overflow-x: auto;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        white-space: nowrap;
    }

    th,
    td {
        padding: 9px 12px;
        text-align: left;
        border-bottom: 1px solid #102510;
    }

    th {
        color: var(--dim);
        font-size: 0.72rem;
        font-weight: normal;
    }

    td {
        color: var(--white);
    }

    tr:last-child td {
        border-bottom: 0;
    }

    .game-link {
        color: var(--green);
        text-decoration: none;
        border-bottom: 1px dotted var(--green);
    }

    .game-link:hover {
        color: var(--white);
        border-bottom-color: var(--white);
    }

    .active {
        color: var(--green);
    }

    .finished {
        color: #8ba58e;
    }

    .declined {
        color: var(--red);
    }

    .two-columns {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
    }

    #last-refresh {
        color: var(--dim);
    }

    .empty {
        padding: 15px;
        color: var(--dim);
    }

    @media (max-width: 900px) {
        .stats {
            grid-template-columns: repeat(2, 1fr);
        }

        .two-columns {
            grid-template-columns: 1fr;
        }
    }
</style>
</head>

<body>
<main>

<header>
    <div>
        <h1>CHESSPOST // CONTROL ROOM</h1>
        <div class="sub">
            private operations dashboard
        </div>
    </div>

    <div class="live">
        <span class="blink">●</span>
        LIVE
    </div>
</header>

<div class="stats">
    <div class="stat">
        <div class="label">ACTIVE</div>
        <div class="value" id="active">-</div>
    </div>

    <div class="stat">
        <div class="label">INVITED</div>
        <div class="value" id="invited">-</div>
    </div>

    <div class="stat">
        <div class="label">FINISHED</div>
        <div class="value" id="finished">-</div>
    </div>

    <div class="stat">
        <div class="label">DECLINED</div>
        <div class="value" id="declined">-</div>
    </div>

    <div class="stat">
        <div class="label">TOTAL</div>
        <div class="value" id="total">-</div>
    </div>
</div>


<section>
    <h2>LIVE EVENT STREAM</h2>

    <div class="scroll">
        <table>
            <thead>
                <tr>
                    <th>TIME</th>
                    <th>EVENT</th>
                    <th>GAME</th>
                    <th>ACTOR</th>
                    <th>TARGET</th>
                    <th>DETAIL</th>
                </tr>
            </thead>

            <tbody id="activity"></tbody>
        </table>
    </div>
</section>


<section>
    <h2>ACTIVE GAME MATRIX</h2>

    <div class="scroll">
        <table>
            <thead>
                <tr>
                    <th>GAME</th>
                    <th>WHITE</th>
                    <th>BLACK</th>
                    <th>STATUS</th>
                    <th>MOVES</th>
                    <th>DELAY</th>
                    <th>RESULT</th>
                    <th>UPDATED</th>
                </tr>
            </thead>

            <tbody id="games"></tbody>
        </table>
    </div>
</section>


<div class="two-columns">

<section>
    <h2>MOVE STREAM</h2>

    <div class="scroll">
        <table>
            <thead>
                <tr>
                    <th>TIME</th>
                    <th>GAME</th>
                    <th>PLAYER</th>
                    <th>MOVE</th>
                </tr>
            </thead>

            <tbody id="moves"></tbody>
        </table>
    </div>
</section>


<section>
    <h2>INBOUND WEBHOOK STREAM</h2>

    <div class="scroll">
        <table>
            <thead>
                <tr>
                    <th>TIME</th>
                    <th>EMAIL ID</th>
                    <th>STATUS</th>
                </tr>
            </thead>

            <tbody id="events"></tbody>
        </table>
    </div>
</section>

</div>

<p id="last-refresh">
    waiting for telemetry...
</p>

</main>


<script>
function esc(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function short(value, length = 14) {
    const text = String(value ?? "");

    if (text.length <= length) {
        return text;
    }

    return text.slice(0, length) + "…";
}


function date(value) {
    if (!value) {
        return "-";
    }

    return new Date(value).toLocaleString();
}


async function refresh() {
    try {
        const response = await fetch("/admin/data", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(
                "HTTP " + response.status
            );
        }

        const data = await response.json();

        for (const key of [
            "active",
            "invited",
            "finished",
            "declined",
            "total"
        ]) {
            document.getElementById(key).textContent =
                data.counts[key];
        }


        const activity =
            document.getElementById("activity");

        activity.innerHTML =
            data.activity_events.length
            ? data.activity_events.map(event => `
                <tr>
                    <td>${esc(date(event.created_at))}</td>

                    <td>
                        ${esc(
                            event.event_type
                                .toUpperCase()
                        )}
                    </td>

                    <td>
                        ${
                            event.game_code
                            ? `
                                <a
                                    class="game-link"
                                    href="/admin/game/${
                                        encodeURIComponent(
                                            event.game_code
                                        )
                                    }"
                                >
                                    ${
                                        esc(
                                            event.game_code
                                                .slice(0, 8)
                                                .toUpperCase()
                                        )
                                    }
                                </a>
                            `
                            : "-"
                        }
                    </td>

                    <td title="${esc(event.actor_email || "")}">
                        ${esc(
                            short(
                                event.actor_email || "-",
                                24
                            )
                        )}
                    </td>

                    <td title="${esc(event.target_email || "")}">
                        ${esc(
                            short(
                                event.target_email || "-",
                                24
                            )
                        )}
                    </td>

                    <td>
                        ${esc(event.detail || "-")}
                    </td>
                </tr>
            `).join("")
            : `
                <tr>
                    <td
                        colspan="6"
                        class="empty"
                    >
                        WAITING FOR ACTIVITY...
                    </td>
                </tr>
            `;


        const games = document.getElementById("games");

        games.innerHTML = data.games.length
            ? data.games.map(game => `
                <tr>
                    <td>
                        <a
                            class="game-link"
                            href="/admin/game/${encodeURIComponent(game.code)}"
                        >
                            ${esc(game.code.slice(0, 8).toUpperCase())}
                        </a>
                    </td>
                    <td>${esc(game.white_email)}</td>
                    <td>${esc(game.black_email)}</td>
                    <td class="${esc(game.status)}">${esc(game.status)}</td>
                    <td>${esc(Math.ceil(game.plies / 2))}</td>
                    <td>${esc(game.delivery_delay_hours)}h</td>
                    <td>${esc(game.result || "-")}</td>
                    <td>${esc(date(game.updated_at))}</td>
                </tr>
            `).join("")
            : `<tr><td colspan="8" class="empty">NO GAMES</td></tr>`;


        const moves = document.getElementById("moves");

        moves.innerHTML = data.moves.length
            ? data.moves.map(move => `
                <tr>
                    <td>${esc(date(move.created_at))}</td>
                    <td>${esc(move.game_code.slice(0, 8).toUpperCase())}</td>
                    <td title="${esc(move.player_email)}">
                        ${esc(short(move.player_email, 22))}
                    </td>
                    <td>${esc(move.san)}</td>
                </tr>
            `).join("")
            : `<tr><td colspan="4" class="empty">NO MOVES</td></tr>`;


        const events = document.getElementById("events");

        events.innerHTML = data.inbound_events.length
            ? data.inbound_events.map(event => `
                <tr>
                    <td>${esc(date(event.first_seen_at))}</td>
                    <td title="${esc(event.email_id)}">
                        ${esc(short(event.email_id, 20))}
                    </td>
                    <td>${esc(event.status)}</td>
                </tr>
            `).join("")
            : `<tr><td colspan="3" class="empty">NO EVENTS</td></tr>`;


        document.getElementById(
            "last-refresh"
        ).textContent =
            "last telemetry refresh: " +
            new Date().toLocaleTimeString();

    } catch (error) {
        document.getElementById(
            "last-refresh"
        ).textContent =
            "telemetry error: " + error;
    }
}


refresh();
setInterval(refresh, 3000);
</script>

</body>
</html>
"""


@router.get(
    "/admin",
    response_class=HTMLResponse,
)
def admin_page(
    _: str = Depends(require_admin),
) -> HTMLResponse:
    return HTMLResponse(ADMIN_HTML)


@router.get("/admin/data")
def admin_data(
    _: str = Depends(require_admin),
) -> dict[str, object]:
    return get_admin_snapshot()


GAME_ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Chesspost Game Inspector</title>

<style>
    :root {
        color-scheme: dark;
        --bg: #050805;
        --panel: #091009;
        --line: #183218;
        --green: #59ff72;
        --dim: #72a278;
        --white: #dfffe3;
        --red: #ff6464;
    }

    * {
        box-sizing: border-box;
    }

    body {
        margin: 0;
        background: var(--bg);
        color: var(--green);
        font-family:
            "Courier New",
            Courier,
            monospace;
        font-size: 14px;
    }

    main {
        width: min(1450px, calc(100% - 30px));
        margin: 25px auto 60px;
    }

    a {
        color: var(--green);
    }

    .back {
        display: inline-block;
        margin-bottom: 22px;
        color: var(--dim);
        text-decoration: none;
    }

    .back:hover {
        color: var(--green);
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 20px;
        margin-bottom: 25px;
    }

    h1 {
        margin: 0;
        font-size: clamp(1.4rem, 4vw, 2.2rem);
        letter-spacing: 0.08em;
    }

    .sub {
        margin-top: 8px;
        color: var(--dim);
    }

    .live {
        border: 1px solid var(--green);
        padding: 7px 10px;
    }

    .blink {
        animation: blink 1.2s step-end infinite;
    }

    @keyframes blink {
        50% {
            opacity: 0;
        }
    }

    .layout {
        display: grid;
        grid-template-columns:
            minmax(320px, 560px)
            1fr;
        gap: 20px;
        align-items: start;
    }

    .panel {
        border: 1px solid var(--line);
        background: var(--panel);
    }

    .panel-title {
        padding: 10px 12px;
        border-bottom: 1px solid var(--line);
        font-size: 0.85rem;
        letter-spacing: 0.12em;
    }

    .board-wrap {
        padding: 18px;
    }

    #board {
        display: block;
        width: 100%;
        height: auto;
    }

    .stats {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
    }

    .stat {
        min-height: 92px;
        padding: 14px;
        border-right: 1px solid var(--line);
        border-bottom: 1px solid var(--line);
    }

    .stat:nth-child(even) {
        border-right: 0;
    }

    .label {
        color: var(--dim);
        font-size: 0.72rem;
        margin-bottom: 8px;
    }

    .value {
        color: var(--white);
        overflow-wrap: anywhere;
    }

    .active {
        color: var(--green);
    }

    .finished {
        color: var(--dim);
    }

    .declined {
        color: var(--red);
    }

    section {
        margin-top: 20px;
        border: 1px solid var(--line);
        background: var(--panel);
    }

    section h2 {
        margin: 0;
        padding: 10px 12px;
        border-bottom: 1px solid var(--line);
        font-size: 0.85rem;
        letter-spacing: 0.12em;
    }

    .scroll {
        overflow-x: auto;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        white-space: nowrap;
    }

    th,
    td {
        padding: 9px 12px;
        text-align: left;
        border-bottom: 1px solid #102510;
    }

    th {
        color: var(--dim);
        font-size: 0.72rem;
        font-weight: normal;
    }

    td {
        color: var(--white);
    }

    tr:last-child td {
        border-bottom: 0;
    }

    .move {
        color: var(--green);
        font-weight: bold;
    }

    .empty {
        padding: 15px;
        color: var(--dim);
    }

    #refresh {
        margin-top: 18px;
        color: var(--dim);
    }

    @media (max-width: 900px) {
        .layout {
            grid-template-columns: 1fr;
        }
    }
</style>
</head>

<body>

<main>

<a class="back" href="/admin">
    &lt; RETURN TO CONTROL ROOM
</a>

<header>
    <div>
        <h1 id="title">
            CHESSPOST // GAME INSPECTOR
        </h1>

        <div class="sub" id="subtitle">
            loading game telemetry...
        </div>
    </div>

    <div class="live">
        <span class="blink">●</span>
        LIVE
    </div>
</header>


<div class="layout">

    <div>
        <div class="panel">
            <div class="panel-title">
                CURRENT BOARD
            </div>

            <div class="board-wrap">
                <img
                    id="board"
                    alt="Current chess position"
                >
            </div>
        </div>
    </div>


    <div class="panel">

        <div class="panel-title">
            GAME STATE
        </div>

        <div class="stats">

            <div class="stat">
                <div class="label">STATUS</div>
                <div class="value" id="status">-</div>
            </div>

            <div class="stat">
                <div class="label">RESULT</div>
                <div class="value" id="result">-</div>
            </div>

            <div class="stat">
                <div class="label">WHITE</div>
                <div class="value" id="white">-</div>
            </div>

            <div class="stat">
                <div class="label">BLACK</div>
                <div class="value" id="black">-</div>
            </div>

            <div class="stat">
                <div class="label">TURN</div>
                <div class="value" id="turn">-</div>
            </div>

            <div class="stat">
                <div class="label">MOVE</div>
                <div class="value" id="move-number">-</div>
            </div>

            <div class="stat">
                <div class="label">DELIVERY DELAY</div>
                <div class="value" id="delay">-</div>
            </div>

            <div class="stat">
                <div class="label">CHECK</div>
                <div class="value" id="check">-</div>
            </div>

        </div>
    </div>

</div>


<section>
    <h2>MOVE HISTORY</h2>

    <div class="scroll">
        <table>
            <thead>
                <tr>
                    <th>PLY</th>
                    <th>MOVE</th>
                    <th>PLAYER</th>
                    <th>TIME</th>
                </tr>
            </thead>

            <tbody id="moves"></tbody>
        </table>
    </div>
</section>


<section>
    <h2>GAME EVENT TIMELINE</h2>

    <div class="scroll">
        <table>
            <thead>
                <tr>
                    <th>TIME</th>
                    <th>EVENT</th>
                    <th>ACTOR</th>
                    <th>TARGET</th>
                    <th>DETAIL</th>
                </tr>
            </thead>

            <tbody id="activity"></tbody>
        </table>
    </div>
</section>


<p id="refresh">
    waiting for telemetry...
</p>

</main>


<script>
const gameCode = decodeURIComponent(
    window.location.pathname
        .split("/")
        .filter(Boolean)
        .pop()
);


function esc(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function date(value) {
    if (!value) {
        return "-";
    }

    return new Date(value).toLocaleString();
}


function short(value, length = 30) {
    const text = String(value ?? "");

    if (text.length <= length) {
        return text;
    }

    return text.slice(0, length) + "…";
}


async function refresh() {
    try {
        const response = await fetch(
            `/admin/game/${encodeURIComponent(gameCode)}/data`,
            {
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                "HTTP " + response.status
            );
        }

        const data = await response.json();
        const game = data.game;

        document.getElementById(
            "title"
        ).textContent =
            "CHESSPOST // GAME " +
            game.code.slice(0, 8).toUpperCase();

        document.getElementById(
            "subtitle"
        ).textContent =
            "created " + date(game.created_at);

        const status =
            document.getElementById("status");

        status.textContent =
            game.status.toUpperCase();

        status.className =
            "value " + game.status;

        document.getElementById(
            "result"
        ).textContent =
            game.result || "-";

        document.getElementById(
            "white"
        ).textContent =
            game.white_email;

        document.getElementById(
            "black"
        ).textContent =
            game.black_email;

        document.getElementById(
            "turn"
        ).textContent =
            game.turn_email || "-";

        document.getElementById(
            "move-number"
        ).textContent =
            game.fullmove_number;

        document.getElementById(
            "delay"
        ).textContent =
            game.delivery_delay_hours === 0
            ? "IMMEDIATE"
            : game.delivery_delay_hours + " HOURS";

        document.getElementById(
            "check"
        ).textContent =
            game.in_check
            ? "YES"
            : "NO";


        const moves =
            document.getElementById("moves");

        moves.innerHTML =
            data.moves.length
            ? data.moves.map(move => `
                <tr>
                    <td>${esc(move.ply)}</td>

                    <td class="move">
                        ${esc(move.san)}
                    </td>

                    <td>
                        ${esc(move.player_email)}
                    </td>

                    <td>
                        ${esc(date(move.created_at))}
                    </td>
                </tr>
            `).join("")
            : `
                <tr>
                    <td
                        colspan="4"
                        class="empty"
                    >
                        NO MOVES YET
                    </td>
                </tr>
            `;


        const activity =
            document.getElementById("activity");

        activity.innerHTML =
            data.activity.length
            ? data.activity.map(event => `
                <tr>
                    <td>
                        ${esc(date(event.created_at))}
                    </td>

                    <td>
                        ${esc(
                            event.event_type
                                .toUpperCase()
                        )}
                    </td>

                    <td title="${esc(event.actor_email || "")}">
                        ${esc(
                            short(
                                event.actor_email || "-",
                                28
                            )
                        )}
                    </td>

                    <td title="${esc(event.target_email || "")}">
                        ${esc(
                            short(
                                event.target_email || "-",
                                28
                            )
                        )}
                    </td>

                    <td>
                        ${esc(event.detail || "-")}
                    </td>
                </tr>
            `).join("")
            : `
                <tr>
                    <td
                        colspan="5"
                        class="empty"
                    >
                        NO RECORDED ACTIVITY
                    </td>
                </tr>
            `;


        document.getElementById(
            "board"
        ).src =
            `/admin/game/${
                encodeURIComponent(gameCode)
            }/board.svg?t=${Date.now()}`;


        document.getElementById(
            "refresh"
        ).textContent =
            "last telemetry refresh: " +
            new Date().toLocaleTimeString();

    } catch (error) {
        document.getElementById(
            "refresh"
        ).textContent =
            "telemetry error: " + error;
    }
}


refresh();
setInterval(refresh, 3000);
</script>

</body>
</html>
"""


@router.get(
    "/admin/game/{game_code}",
    response_class=HTMLResponse,
)
def admin_game_page(
    game_code: str,
    _: str = Depends(require_admin),
) -> HTMLResponse:
    # Validate that the game exists before displaying the page.
    get_game_snapshot(game_code)

    return HTMLResponse(
        GAME_ADMIN_HTML
    )


@router.get(
    "/admin/game/{game_code}/data",
)
def admin_game_data(
    game_code: str,
    _: str = Depends(require_admin),
) -> dict[str, object]:
    return get_game_snapshot(
        game_code
    )


@router.get(
    "/admin/game/{game_code}/board.svg",
)
def admin_game_board(
    game_code: str,
    _: str = Depends(require_admin),
) -> Response:
    svg = get_game_board_svg(
        game_code
    )

    return Response(
        content=svg,
        media_type="image/svg+xml",
    )
