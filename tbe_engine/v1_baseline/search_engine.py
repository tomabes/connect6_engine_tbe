"""Depth-limited minimax. No alpha-beta pruning or quiescence search."""

from itertools import combinations
import time

from defines import Defines, StoneMove
from tools import DIRECTIONS, empty_points, isValidPos, is_win_by_premove, make_move, unmake_move


# All six-intersection windows, including lines containing gaps between stones.
WINDOWS = []
POINT_WINDOWS = {(x, y): [] for x in range(1, 20) for y in range(1, 20)}
for x in range(1, 20):
    for y in range(1, 20):
        for dx, dy in DIRECTIONS:
            if isValidPos(x + 5 * dx, y + 5 * dy):
                window = tuple((x + i * dx, y + i * dy) for i in range(6))
                WINDOWS.append(window)
                for point in window:
                    POINT_WINDOWS[point].append(window)


class SearchTimeout(Exception):
    """The turn's search budget is exhausted."""


class SearchEngine:
    def __init__(self):
        self.deadline = None
        self.stats = {}

    def check_time(self):
        if self.deadline is not None and time.perf_counter() >= self.deadline:
            raise SearchTimeout()

    def local_points(self, board):
        occupied = [(x, y) for x in range(1, 20) for y in range(1, 20)
                    if board[x][y] in (Defines.BLACK, Defines.WHITE)]
        if not occupied:
            return [(10, 10)]
        points = set()
        radius = Defines.SEARCH_RADIUS
        for x, y in occupied:
            for xx in range(max(1, x - radius), min(19, x + radius) + 1):
                for yy in range(max(1, y - radius), min(19, y + radius) + 1):
                    if board[xx][yy] == Defines.NOSTONE:
                        points.add((xx, yy))
        return sorted(points)

    def point_score(self, board, point):
        # A deliberately simple, colour-neutral way to select a small local pool.
        score = 0
        for window in POINT_WINDOWS[point]:
            black = white = 0
            for x, y in window:
                black += board[x][y] == Defines.BLACK
                white += board[x][y] == Defines.WHITE
            if black == 0 or white == 0:
                score += black * black + white * white
        return score

    def generate_moves(self, board, color):
        points = self.local_points(board)
        self.check_time()
        if not points:
            return []
        if len(points) == 1:
            return [StoneMove(points[0])]
        scored = []
        for point in points:
            self.check_time()
            scored.append((self.point_score(board, point), point))
        scored.sort(key=lambda item: (-item[0], abs(item[1][0] - 10) + abs(item[1][1] - 10), item[1]))
        scored = scored[:Defines.MAX_POINTS]
        # First black turn is the only normal turn with a single stone.
        if len(empty_points(board)) == Defines.GRID_COUNT and color == Defines.BLACK:
            return [StoneMove((10, 10))]
        pairs = [(score_a + score_b, first, second)
                 for (score_a, first), (score_b, second) in combinations(scored, 2)]
        pairs.sort(key=lambda item: -item[0])
        return [StoneMove(first, second) for _, first, second in pairs[:Defines.MAX_MOVES]]

    def evaluate(self, board):
        # Positive means Black is ahead. Count potential six-windows weighted
        # only by their number of stones; richer threat patterns belong to v3.
        score = 0
        for i, window in enumerate(WINDOWS):
            if i % 32 == 0:
                self.check_time()
            black = white = 0
            for x, y in window:
                black += board[x][y] == Defines.BLACK
                white += board[x][y] == Defines.WHITE
            if black == 6:
                return Defines.WIN_SCORE
            if white == 6:
                return -Defines.WIN_SCORE
            if white == 0:
                score += black
            if black == 0:
                score -= white
        return score

    def minimax(self, board, depth, color, previous_move):
        self.check_time()
        self.stats["nodes"] += 1
        if is_win_by_premove(board, previous_move):
            p = previous_move.positions[0]
            return Defines.WIN_SCORE if board[p.x][p.y] == Defines.BLACK else -Defines.WIN_SCORE
        if not empty_points(board):
            return 0
        if depth == 0:
            return self.evaluate(board)
        best = -float("inf") if color == Defines.BLACK else float("inf")
        for move in self.generate_moves(board, color):
            self.check_time()
            make_move(board, move, color)
            try:
                score = self.minimax(board, depth - 1, color ^ 3, move)
            finally:
                unmake_move(board, move)
            best = max(best, score) if color == Defines.BLACK else min(best, score)
        return best

    def choose_move(self, board, color, time_limit):
        started = time.perf_counter()
        # Reserve a little time for restoring state, metrics and the protocol reply.
        self.deadline = started + time_limit - min(0.02, time_limit * 0.1)
        self.stats = {"nodes": 0, "pruned": 0, "depth_reached": 0, "timed_out": False}
        points = self.local_points(board)
        if not points:
            return None
        if len(empty_points(board)) == Defines.GRID_COUNT:
            if color != Defines.BLACK:
                raise ValueError("Black must make the first move")
            best_move = StoneMove((10, 10))
            self.stats["seconds"] = time.perf_counter() - started
            return best_move
        # A legal initial choice is available even if the search budget is tiny.
        best_move = StoneMove(points[0], points[1] if len(points) > 1 else None)
        try:
            candidates = self.generate_moves(board, color)
            best_move = candidates[0]
            # Both iterations have a fixed depth bound; an incomplete deeper
            # iteration never replaces the last fully completed result.
            for depth in range(1, Defines.MAX_DEPTH + 1):
                best_score = -float("inf") if color == Defines.BLACK else float("inf")
                depth_move = candidates[0]
                for move in candidates:
                    self.check_time()
                    make_move(board, move, color)
                    try:
                        score = self.minimax(board, depth - 1, color ^ 3, move)
                    finally:
                        unmake_move(board, move)
                    if (color == Defines.BLACK and score > best_score) or (color == Defines.WHITE and score < best_score):
                        best_score, depth_move = score, move
                best_move = depth_move
                best_move.score = best_score
                self.stats["depth_reached"] = depth
        except SearchTimeout:
            self.stats["timed_out"] = True
        self.stats["seconds"] = time.perf_counter() - started
        return best_move
