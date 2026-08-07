import base64

from fastapi.testclient import TestClient

from app import app
from database import create_game
from game_service import submit_move


client = TestClient(app)


def auth_headers(
    username: str,
    password: str,
) -> dict[str, str]:
    value = base64.b64encode(
        f"{username}:{password}".encode()
    ).decode()

    return {
        "Authorization": f"Basic {value}"
    }


def configure_admin(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv(
        "CHESSPOST_DATABASE",
        str(tmp_path / "admin.db"),
    )

    monkeypatch.setenv(
        "CHESSPOST_ADMIN_USER",
        "admin",
    )

    monkeypatch.setenv(
        "CHESSPOST_ADMIN_PASSWORD",
        "secret-test-password",
    )


def test_admin_requires_authentication(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(monkeypatch, tmp_path)

    response = client.get("/admin")

    assert response.status_code == 401


def test_wrong_admin_password_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(monkeypatch, tmp_path)

    response = client.get(
        "/admin",
        headers=auth_headers(
            "admin",
            "wrong-password",
        ),
    )

    assert response.status_code == 401


def test_admin_page_loads(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(monkeypatch, tmp_path)

    response = client.get(
        "/admin",
        headers=auth_headers(
            "admin",
            "secret-test-password",
        ),
    )

    assert response.status_code == 200
    assert "CHESSPOST // CONTROL ROOM" in response.text


def test_admin_data_contains_games_and_moves(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(monkeypatch, tmp_path)

    database_path = tmp_path / "admin.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    submit_move(
        game.code,
        "white@example.com",
        "e4",
        database_path,
    )

    response = client.get(
        "/admin/data",
        headers=auth_headers(
            "admin",
            "secret-test-password",
        ),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "online"
    assert data["counts"]["active"] == 1
    assert len(data["games"]) == 1
    assert len(data["moves"]) == 1
    assert data["moves"][0]["san"] == "e4"


def test_game_inspector_page_loads(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(
        monkeypatch,
        tmp_path,
    )

    database_path = tmp_path / "admin.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = client.get(
        f"/admin/game/{game.code}",
        headers=auth_headers(
            "admin",
            "secret-test-password",
        ),
    )

    assert response.status_code == 200
    assert "GAME INSPECTOR" in response.text


def test_game_inspector_data_contains_position(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(
        monkeypatch,
        tmp_path,
    )

    database_path = tmp_path / "admin.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    submit_move(
        game.code,
        "white@example.com",
        "e4",
        database_path,
    )

    response = client.get(
        f"/admin/game/{game.code}/data",
        headers=auth_headers(
            "admin",
            "secret-test-password",
        ),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["game"]["code"] == game.code
    assert data["game"]["status"] == "active"
    assert data["game"]["turn_email"] == "black@example.com"

    assert len(data["moves"]) == 1
    assert data["moves"][0]["san"] == "e4"


def test_game_board_svg_is_available(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(
        monkeypatch,
        tmp_path,
    )

    database_path = tmp_path / "admin.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    response = client.get(
        f"/admin/game/{game.code}/board.svg",
        headers=auth_headers(
            "admin",
            "secret-test-password",
        ),
    )

    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        .startswith("image/svg+xml")
    )
    assert "<svg" in response.text


def test_unknown_game_inspector_returns_404(
    monkeypatch,
    tmp_path,
) -> None:
    configure_admin(
        monkeypatch,
        tmp_path,
    )

    response = client.get(
        "/admin/game/does-not-exist",
        headers=auth_headers(
            "admin",
            "secret-test-password",
        ),
    )

    assert response.status_code == 404
