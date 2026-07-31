import chess

from chess_engine import apply_move, new_game_fen


def show_board(fen: str) -> None:
    board = chess.Board(fen)

    print()
    print(board)
    print()

    turn = "White" if board.turn == chess.WHITE else "Black"
    print(f"Turn: {turn}")
    print(f"FEN: {fen}")
    print()


def main() -> None:
    fen = new_game_fen()

    print("Chesspost — Local Chess Test")
    print("Enter moves such as e4, Nf3, Bxc6, or O-O.")
    print("Type 'quit' to stop.")

    while True:
        show_board(fen)

        move_text = input("Move: ").strip()

        if move_text.lower() == "quit":
            print("Game stopped.")
            return

        result = apply_move(fen, move_text)
        print(result.message)

        if not result.accepted:
            continue

        fen = result.fen

        if result.game_over:
            show_board(fen)
            print(f"Game over. Result: {result.result}")
            return


if __name__ == "__main__":
    main()
