"""V4 search settings and the manual reference weights used to initialise GA."""


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
    EVAL_WEIGHTS = {
        "line_1": LINE_WEIGHTS[1],
        "line_2": LINE_WEIGHTS[2],
        "line_3": LINE_WEIGHTS[3],
        "line_4": LINE_WEIGHTS[4],
        "line_5": LINE_WEIGHTS[5],
        "threat_1": 600,
        "threat_2": 3000,
        "threat_3": 15000,  # At least three defending stones would be needed.
        "connectivity": 2,
    }
    SEARCH_RADIUS = 3
    MAX_POINTS = 12
    MAX_MOVES = 24
    MAX_DEPTH = 2  # Depth counts complete turns, not individual stones.
    Q_MAX_DEPTH = 1  # One tactical turn; two caused normal depth-2 timeouts.
    FP_PRESELECT = 24  # Ordinary pairs kept before expensive v3 analysis.
    FP_MAX_QUIET_MOVES = 8  # Ordinary quiet pairs kept after ordering.
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
