from chess_engine import apply_move, new_game_fen


def test_new_game_accepts_e4() -> None:
    starting_fen = new_game_fen()

    result = apply_move(starting_fen, "e4")

    assert result.accepted is True
    assert result.move == "e4"
    assert result.fen != starting_fen
    assert result.game_over is False
    assert result.result is None


def test_illegal_move_is_rejected() -> None:
    starting_fen = new_game_fen()

    result = apply_move(starting_fen, "e5")

    assert result.accepted is False
    assert result.fen == starting_fen
    assert result.move is None


def test_empty_move_is_rejected() -> None:
    starting_fen = new_game_fen()

    result = apply_move(starting_fen, "   ")

    assert result.accepted is False
    assert result.message == "No move was provided."
    assert result.fen == starting_fen


def test_fools_mate_ends_the_game() -> None:
    fen = new_game_fen()

    for move_text in ["f3", "e5", "g4"]:
        result = apply_move(fen, move_text)
        assert result.accepted is True
        fen = result.fen

    result = apply_move(fen, "Qh4#")

    assert result.accepted is True
    assert result.move == "Qh4#"
    assert result.game_over is True
    assert result.result == "0-1"
