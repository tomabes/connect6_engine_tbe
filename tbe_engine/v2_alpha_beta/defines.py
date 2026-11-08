"""The v1 board representation and parameters, with v2 evaluation weights."""


class Defines:
    GRID_NUM = 21  # 19 playable intersections plus a border on each side.
    GRID_COUNT = 361
    BLACK = 1
    WHITE = 2
    BORDER = 3
    NOSTONE = 0
    ENGINE_NAME = "tbe"
    WIN_SCORE = 1_000_000
    LINE_WEIGHTS = (0, 1, 4, 16, 64, 256, WIN_SCORE)
    SEARCH_RADIUS = 3
    MAX_POINTS = 12
    MAX_MOVES = 24
    MAX_DEPTH = 2  # Depth counts complete turns, not individual stones.
    TIME_LIMIT = 5.0  # Seconds per turn; the command `depth` changes this.


class StonePosition:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class StoneMove:
    def __init__(self, first=(0, 0), second=None):
        # The teacher's representation repeats a point for a one-stone move.
        if second is None:
            second = first
        self.positions = [StonePosition(*first), StonePosition(*second)]
        self.score = 0
