from database import create_game
from game_service import resign_game, submit_move
from game_summary import summarize_game


def test_resignation_declares_opponent_winner(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    result = resign_game(
        game.code,
        "white@example.com",
        database_path,
    )

    assert result.accepted is True
    assert result.game.status == "finished"
    assert result.game.result == "0-1"

    summary = summarize_game(
        result.game,
        database_path,
        termination_override="Resignation",
    )

    assert summary.winner_email == "black@example.com"
    assert summary.white_wins == 0
    assert summary.black_wins == 1
    assert summary.draws == 0


def test_summary_counts_chess_move_numbers(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    game = create_game(
        "white@example.com",
        "black@example.com",
        database_path,
    )

    moves = [
        ("white@example.com", "f3"),
        ("black@example.com", "e5"),
        ("white@example.com", "g4"),
        ("black@example.com", "Qh4#"),
    ]

    final_game = game

    for email, move in moves:
        result = submit_move(
            game.code,
            email,
            move,
            database_path,
        )
        final_game = result.game

    summary = summarize_game(
        final_game,
        database_path,
    )

    assert final_game.status == "finished"
    assert summary.plies == 4
    assert summary.move_number == 2
    assert summary.winner_email == "black@example.com"
    assert summary.termination == "Checkmate"
