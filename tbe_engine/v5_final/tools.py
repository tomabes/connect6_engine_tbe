"""Coordinates, legal placement and terminal positions."""

from defines import Defines, StoneMove


DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))


def isValidPos(x, y):
    return 1 <= x < Defines.GRID_NUM - 1 and 1 <= y < Defines.GRID_NUM - 1


def init_board(board):
    for x in range(Defines.GRID_NUM):
        for y in range(Defines.GRID_NUM):
            board[x][y] = Defines.NOSTONE if isValidPos(x, y) else Defines.BORDER


def move_points(move):
    first, second = ((p.x, p.y) for p in move.positions)
    return (first,) if first == second else (first, second)


def make_move(board, move, color):
    if color not in (Defines.BLACK, Defines.WHITE):
        raise ValueError("Stone colour must be black or white")
    points = move_points(move)
    # Validate both cells before changing the board.
    for x, y in points:
        if not isValidPos(x, y):
            raise ValueError("Stone position is outside the board")
        if board[x][y] != Defines.NOSTONE:
            raise ValueError("Stone position is already occupied")
    for x, y in points:
        board[x][y] = color


def unmake_move(board, move):
    for x, y in move_points(move):
        board[x][y] = Defines.NOSTONE


def msg2move(msg):
    msg = msg.strip().upper()
    if len(msg) not in (2, 4) or any(c < "A" or c > "S" for c in msg):
        raise ValueError("A move must contain two or four letters from A to S")
    # Preserve the teacher's internal coordinate orientation.
    first = (ord("S") - ord(msg[1]) + 1, ord(msg[0]) - ord("A") + 1)
    second = None
    if len(msg) == 4:
        second = (ord("S") - ord(msg[3]) + 1, ord(msg[2]) - ord("A") + 1)
    return StoneMove(first, second)


def move2msg(move):
    return "".join(chr(y + ord("A") - 1) + chr(ord("S") - x + 1)
                   for x, y in move_points(move))


def is_win_from(board, x, y):
    if not isValidPos(x, y):
        return False
    color = board[x][y]
    if color not in (Defines.BLACK, Defines.WHITE):
        return False
    for dx, dy in DIRECTIONS:
        count = 1
        for sign in (-1, 1):
            xx, yy = x + sign * dx, y + sign * dy
            while board[xx][yy] == color:
                count += 1
                xx += sign * dx
                yy += sign * dy
        if count >= 6:
            return True
    return False


def is_win_by_premove(board, preMove):
    return any(is_win_from(board, x, y) for x, y in move_points(preMove))


def board_winner(board):
    # Full scan is needed when a position is loaded through black/white commands.
    for x in range(1, Defines.GRID_NUM - 1):
        for y in range(1, Defines.GRID_NUM - 1):
            if board[x][y] in (Defines.BLACK, Defines.WHITE) and is_win_from(board, x, y):
                return board[x][y]
    return Defines.NOSTONE


def empty_points(board):
    return [(x, y) for x in range(1, Defines.GRID_NUM - 1)
            for y in range(1, Defines.GRID_NUM - 1) if board[x][y] == Defines.NOSTONE]


def print_board(board):
    letters = "ABCDEFGHIJKLMNOPQRS"
    symbols = {Defines.NOSTONE: ".", Defines.BLACK: "B", Defines.WHITE: "W"}
    print("  " + " ".join(letters))
    for row, letter in enumerate(letters):
        print(letter + " " + " ".join(symbols[board[19 - col][row + 1]] for col in range(19)))
