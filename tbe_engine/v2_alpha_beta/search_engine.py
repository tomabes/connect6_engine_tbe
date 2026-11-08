"""V1 minimax extended with alpha-beta, move ordering and weighted lines."""

from itertools import combinations
import time

from defines import Defines, StoneMove
from tools import DIRECTIONS, empty_points, isValidPos, is_win_by_premove, make_move, move_points, unmake_move


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

    def window_score(self, black, white):
        if black and white:
            return 0
        return Defines.LINE_WEIGHTS[black] - Defines.LINE_WEIGHTS[white]

    def point_score(self, board, point, color):
        # Combine attacking potential and the opponent's potential at this cell.
        score = 0
        for window in POINT_WINDOWS[point]:
            black = white = 0
            for x, y in window:
                black += board[x][y] == Defines.BLACK
                white += board[x][y] == Defines.WHITE
            before = self.window_score(black, white)
            black_gain = self.window_score(black + 1, white) - before
            white_gain = before - self.window_score(black, white + 1)
            own_gain, enemy_gain = (black_gain, white_gain) if color == Defines.BLACK else (white_gain, black_gain)
            score += 2 * own_gain + enemy_gain
        return score

    def winning_completions(self, board, color):
        # Each entry contains the one or two empty cells needed for an immediate
        # six. Overlapping windows are kept as constraints, not counted as
        # independent threats. Own wins take priority over defending.
        completions = set()
        for i, window in enumerate(WINDOWS):
            if i % 32 == 0:
                self.check_time()
            empty = []
            for x, y in window:
                value = board[x][y]
                if value == (color ^ 3):
                    break
                if value == Defines.NOSTONE:
                    empty.append((x, y))
            else:
                if 1 <= len(empty) <= 2:
                    completions.add(tuple(sorted(empty)))
        return sorted(completions, key=lambda cells: (len(cells), cells))

    def defensive_moves(self, completions, ranked_points):
        # A defence must occupy at least one cell of EVERY winning completion.
        # Pick a cell from the first constraint, then intersect those it misses.
        moves = []
        for first in completions[0]:
            uncovered = [cells for cells in completions if first not in cells]
            if uncovered:
                seconds = set(uncovered[0])
                for cells in uncovered[1:]:
                    seconds.intersection_update(cells)
                seconds = sorted(seconds)
            else:
                seconds = [point for point in ranked_points if point != first]
            moves.extend(StoneMove(first, second) for second in seconds)
        return moves

    def move_score(self, board, move, color):
        # The two stones may improve the SAME window. Score their joint effect,
        # rather than adding two independent point scores as in v1.
        points = move_points(move)
        affected = set()
        for point in points:
            affected.update(POINT_WINDOWS[point])
        delta = 0
        for window in affected:
            black = white = 0
            for x, y in window:
                black += board[x][y] == Defines.BLACK
                white += board[x][y] == Defines.WHITE
            before = self.window_score(black, white)
            added = sum(point in window for point in points)
            if color == Defines.BLACK:
                black += added
            else:
                white += added
            delta += self.window_score(black, white) - before
        return delta if color == Defines.BLACK else -delta

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
            scored.append((self.point_score(board, point, color), point))
        scored.sort(key=lambda item: (-item[0], abs(item[1][0] - 10) + abs(item[1][1] - 10), item[1]))
        scored = scored[:Defines.MAX_POINTS]
        # First black turn is the only normal turn with a single stone.
        if len(empty_points(board)) == Defines.GRID_COUNT and color == Defines.BLACK:
            return [StoneMove((10, 10))]
        ranked_points = [point for _, point in scored]
        wins = self.winning_completions(board, color)
        if wins:
            moves = []
            for cells in wins:
                first = cells[0]
                second = cells[1] if len(cells) == 2 else next(point for point in ranked_points if point != first)
                moves.append(StoneMove(first, second))
        else:
            enemy_wins = self.winning_completions(board, color ^ 3)
            moves = self.defensive_moves(enemy_wins, ranked_points) if enemy_wins else []
            if not moves:
                # With no immediate threat, explore ordinary candidates. If no
                # two-stone defence exists, these moves let the search evaluate
                # the forced loss instead of inventing a successful defence.
                moves = [StoneMove(first, second) for first, second in combinations(ranked_points, 2)]
        unique = {}
        for move in moves:
            self.check_time()
            key = tuple(sorted(move_points(move)))
            if key not in unique:
                unique[key] = (self.move_score(board, move, color), move)
        ordered = sorted(unique.values(), key=lambda item: (-item[0], tuple(sorted(move_points(item[1])))))
        return [move for _, move in ordered[:Defines.MAX_MOVES]]

    def evaluate(self, board):
        # Positive means Black is ahead. Unlike v1's linear count, longer live
        # windows have progressively larger weights. Independent threat counts
        # and the article-based positional features are reserved for v3.
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
            score += self.window_score(black, white)
        return score

    def alpha_beta(self, board, depth, color, previous_move, alpha=-float("inf"), beta=float("inf")):
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
        moves = self.generate_moves(board, color)
        for i, move in enumerate(moves):
            self.check_time()
            make_move(board, move, color)
            try:
                score = self.alpha_beta(board, depth - 1, color ^ 3, move, alpha, beta)
            finally:
                unmake_move(board, move)
            best = max(best, score) if color == Defines.BLACK else min(best, score)
            if color == Defines.BLACK:
                alpha = max(alpha, best)
            else:
                beta = min(beta, best)
            if alpha >= beta:
                skipped = len(moves) - i - 1
                self.stats["pruned"] += skipped
                if skipped:
                    self.stats["cutoffs"] += 1
                break
        return best

    def choose_move(self, board, color, time_limit):
        started = time.perf_counter()
        # Reserve a little time for restoring state, metrics and the protocol reply.
        self.deadline = started + time_limit - min(0.02, time_limit * 0.1)
        self.stats = {"nodes": 0, "pruned": 0, "cutoffs": 0, "depth_reached": 0, "timed_out": False}
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
                alpha, beta = -float("inf"), float("inf")
                for move in candidates:
                    self.check_time()
                    make_move(board, move, color)
                    try:
                        score = self.alpha_beta(board, depth - 1, color ^ 3, move, alpha, beta)
                    finally:
                        unmake_move(board, move)
                    if (color == Defines.BLACK and score > best_score) or (color == Defines.WHITE and score < best_score):
                        best_score, depth_move = score, move
                    if color == Defines.BLACK:
                        alpha = max(alpha, best_score)
                    else:
                        beta = min(beta, best_score)
                best_move = depth_move
                best_move.score = best_score
                self.stats["depth_reached"] = depth
        except SearchTimeout:
            self.stats["timed_out"] = True
        self.stats["seconds"] = time.perf_counter() - started
        return best_move
