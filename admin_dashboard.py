import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from database import connect, init_database
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
                            ? esc(
                                event.game_code
                                    .slice(0, 8)
                                    .toUpperCase()
                            )
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
                    <td>${esc(game.code.slice(0, 8).toUpperCase())}</td>
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
