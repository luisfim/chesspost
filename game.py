import chess


def show_board(board: chess.Board) -> None:
    """Display the current board and whose turn it is."""
    print()
    print(board)
    print()

    turn = "White" if board.turn == chess.WHITE else "Black"
    print(f"Turn: {turn}")
    print(f"FEN: {board.fen()}")
    print()


def main() -> None:
    board = chess.Board()

    print("Chesspost — Local Chess Test")
    print("Enter moves using standard notation, such as e4, Nf3, or O-O.")
    print("Type 'quit' to stop.")

    while not board.is_game_over():
        show_board(board)

        move_text = input("Move: ").strip()

        if move_text.lower() == "quit":
            print("Game stopped.")
            return

        try:
            move = board.parse_san(move_text)
            board.push(move)
            print(f"Accepted move: {move_text}")
        except ValueError:
            print(f"Illegal or unrecognized move: {move_text}")

    show_board(board)
    print(f"Game over: {board.outcome()}")


if __name__ == "__main__":
    main()
