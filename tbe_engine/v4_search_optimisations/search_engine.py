"""V3 evaluation with independently switchable quiescence and forward pruning."""

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


# Maximal board lines are also used for Liu-inspired distance-sensitive
# connections. Opposing stones split each line into separate potential areas.
LINES = []
for dx, dy in DIRECTIONS:
    for x in range(1, 20):
        for y in range(1, 20):
            if isValidPos(x - dx, y - dy):
                continue
            line = []
            xx, yy = x, y
            while isValidPos(xx, yy):
                line.append((xx, yy))
                xx, yy = xx + dx, yy + dy
            if len(line) >= 6:
                LINES.append(tuple(line))


class SearchTimeout(Exception):
    """The turn's search budget is exhausted."""


class SearchEngine:
    def __init__(self, weights=None, use_quiescence=True, use_forward_pruning=True):
        self.deadline = None
        self.use_quiescence = use_quiescence
        self.use_forward_pruning = use_forward_pruning
        self.reset_stats()
        self.weights = dict(Defines.EVAL_WEIGHTS if weights is None else weights)
        if self.weights.keys() != Defines.EVAL_WEIGHTS.keys():
            raise ValueError("Evaluation weights must specify all nine v3 features")

    def reset_stats(self):
        self.stats = {"nodes": 0, "pruned": 0, "cutoffs": 0, "depth_reached": 0,
                      "timed_out": False, "q_nodes": 0, "q_depth_reached": 0,
                      "forward_pruned": 0, "quiescence": self.use_quiescence,
                      "forward_pruning": self.use_forward_pruning}

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
        if black == 6:
            return Defines.WIN_SCORE
        if white == 6:
            return -Defines.WIN_SCORE
        return (self.weights[f"line_{black}"] if black else 0) - (self.weights[f"line_{white}"] if white else 0)

    def point_influence(self, board, point, color):
        # Adapt Liu's local influence: nearby aligned stones contribute more;
        # an opponent stone stops influence. A segment must still fit a six.
        x, y = point
        influence = 0
        for dx, dy in DIRECTIONS:
            available = 1
            connections = 0
            for sign in (-1, 1):
                for distance in range(1, 6):
                    xx, yy = x + sign * distance * dx, y + sign * distance * dy
                    if not isValidPos(xx, yy) or board[xx][yy] == (color ^ 3):
                        break
                    available += 1
                    if board[xx][yy] == color:
                        connections += 6 - distance
            if available >= 6:
                influence += connections
        return influence

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
        score += self.weights["connectivity"] * (
            2 * self.point_influence(board, point, color)
            + self.point_influence(board, point, color ^ 3))
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

    def threat_level(self, completions):
        # Wu-Huang define threat strength as the number of stones needed to
        # defend. Solve that question globally up to two stones, including
        # overlapping windows and crossings between different directions.
        if not completions:
            return 0
        common = set(completions[0])
        for cells in completions[1:]:
            common.intersection_update(cells)
        if common:
            return 1
        for first in completions[0]:
            uncovered = [cells for cells in completions if first not in cells]
            seconds = set(uncovered[0])
            for cells in uncovered[1:]:
                seconds.intersection_update(cells)
            if seconds:
                return 2
        return 3  # No defence with <=2 stones; not an exact count beyond two.

    def connectivity(self, board, color):
        score = 0
        for line in LINES:
            self.check_time()
            values = [board[x][y] for x, y in line]
            start = 0
            for end in range(len(values) + 1):
                if end < len(values) and values[end] != (color ^ 3):
                    continue
                if end - start >= 6:
                    for i in range(start, end):
                        if values[i] == color:
                            for j in range(i + 1, min(end, i + 6)):
                                if values[j] == color:
                                    score += 6 - (j - i)
                start = end + 1
        return score

    def analyse_position(self, board):
        black_features = dict.fromkeys(self.weights, 0)
        white_features = dict.fromkeys(self.weights, 0)
        black_wins, white_wins = set(), set()
        for i, window in enumerate(WINDOWS):
            if i % 32 == 0:
                self.check_time()
            black = white = 0
            empty = []
            for x, y in window:
                value = board[x][y]
                black += value == Defines.BLACK
                white += value == Defines.WHITE
                if value == Defines.NOSTONE:
                    empty.append((x, y))
            if black == 6:
                return black_features, white_features, Defines.WIN_SCORE
            if white == 6:
                return black_features, white_features, -Defines.WIN_SCORE
            if black and white:
                continue
            if black:
                black_features[f"line_{black}"] += 1
                if black >= 4:
                    black_wins.add(tuple(sorted(empty)))
            if white:
                white_features[f"line_{white}"] += 1
                if white >= 4:
                    white_wins.add(tuple(sorted(empty)))
        for features, wins, color in ((black_features, black_wins, Defines.BLACK),
                                      (white_features, white_wins, Defines.WHITE)):
            level = self.threat_level(sorted(wins))
            if level:
                features[f"threat_{level}"] = 1
            features["connectivity"] = self.connectivity(board, color)
        return black_features, white_features, None

    def feature_score(self, black, white):
        return sum(self.weights[name] * (black[name] - white[name]) for name in self.weights)

    def move_score(self, board, move, color):
        make_move(board, move, color)
        try:
            black, white, terminal = self.analyse_position(board)
        finally:
            unmake_move(board, move)
        sign = 1 if color == Defines.BLACK else -1
        value = sign * (terminal if terminal is not None else self.feature_score(black, white))
        own = black if color == Defines.BLACK else white
        pressure = sum(level * own[f"threat_{level}"] for level in (1, 2, 3))
        # Sort by terminal result, then forcing strength, growing live fours/fives,
        # then the weighted position score. This is ordering, not a mate proof.
        result = (1 if value == Defines.WIN_SCORE else -1) if terminal is not None else 0
        return result, pressure, own["line_4"] + own["line_5"], value

    def quick_move_score(self, board, move, color):
        # Cheap local window delta, as in v2. Only used to preselect ordinary
        # pairs before the full v3 threat/connectivity analysis.
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

    def generate_moves(self, board, color, tactical_only=False):
        points = self.local_points(board)
        self.check_time()
        if not points:
            return []
        wins = self.winning_completions(board, color)
        enemy_wins = [] if wins else self.winning_completions(board, color ^ 3)
        critical = bool(wins or enemy_wins)
        if tactical_only and not critical:
            return []  # A quiet leaf needs no ordinary pair generation.
        if len(points) == 1:
            return [StoneMove(points[0])]
        scored = []
        for point in points:
            self.check_time()
            scored.append((self.point_score(board, point, color), point))
        scored.sort(key=lambda item: (-item[0], abs(item[1][0] - 10) + abs(item[1][1] - 10), item[1]))
        scored = scored[:2 * Defines.MAX_POINTS]
        # First black turn is the only normal turn with a single stone.
        if len(empty_points(board)) == Defines.GRID_COUNT and color == Defines.BLACK:
            return [StoneMove((10, 10))]
        ranked_points = [point for _, point in scored]
        if wins:
            moves = []
            for cells in wins:
                first = cells[0]
                second = cells[1] if len(cells) == 2 else next(point for point in ranked_points if point != first)
                moves.append(StoneMove(first, second))
        else:
            moves = self.defensive_moves(enemy_wins, ranked_points) if enemy_wins else []
            if not moves:
                if tactical_only:
                    return []  # The caller distinguishes quiet from forced loss.
                # With no immediate threat, explore ordinary candidates. If no
                # two-stone defence exists, these moves let the search evaluate
                # the forced loss instead of inventing a successful defence.
                # Wu-Huang section 4.3: re-evaluate the second stone AFTER the
                # first. The second pool stays inside the original radius-3 area.
                moves = []
                for i, first in enumerate(ranked_points[:Defines.MAX_POINTS]):
                    first_move = StoneMove(first)
                    make_move(board, first_move, color)
                    try:
                        seconds = []
                        for point in ranked_points:
                            self.check_time()
                            if point != first:
                                seconds.append((self.point_score(board, point, color), point))
                        seconds.sort(key=lambda item: (-item[0], item[1]))
                    finally:
                        unmake_move(board, first_move)
                    width = Defines.MAX_POINTS - i
                    moves.extend(StoneMove(first, second) for _, second in seconds[:width])
        unique = {}
        for move in moves:
            self.check_time()
            key = tuple(sorted(move_points(move)))
            if key not in unique:
                unique[key] = move
        moves = list(unique.values())
        if self.use_forward_pruning and not critical:
            cheap = []
            for move in moves:
                self.check_time()
                cheap.append((self.quick_move_score(board, move, color), move))
            cheap.sort(key=lambda item: (-item[0], tuple(sorted(move_points(item[1])))))
            moves = [move for _, move in cheap[:Defines.FP_PRESELECT]]
            self.stats["forward_pruned"] += len(cheap) - len(moves)
        scored_moves = []
        for move in moves:
            self.check_time()
            scored_moves.append((self.move_score(board, move, color), move))
        ordered = sorted(scored_moves, key=lambda item: (
            -item[0][0], -item[0][1], -item[0][2], -item[0][3], tuple(sorted(move_points(item[1])))))
        if self.use_forward_pruning and not critical:
            selected = []
            quiet_count = 0
            for score, move in ordered:
                if score[0] != 0 or score[1] > 0:
                    selected.append((score, move))
                elif quiet_count < Defines.FP_MAX_QUIET_MOVES:
                    selected.append((score, move))
                    quiet_count += 1
                else:
                    self.stats["forward_pruned"] += 1
            ordered = selected
        return [move for _, move in ordered[:Defines.MAX_MOVES]]

    def evaluate(self, board):
        black, white, terminal = self.analyse_position(board)
        return terminal if terminal is not None else self.feature_score(black, white)

    def quiescence(self, board, color, previous_move, alpha, beta, remaining):
        self.check_time()
        self.stats["nodes"] += 1
        self.stats["q_nodes"] += 1
        self.stats["q_depth_reached"] = max(self.stats["q_depth_reached"], Defines.Q_MAX_DEPTH - remaining)
        if is_win_by_premove(board, previous_move):
            p = previous_move.positions[0]
            return Defines.WIN_SCORE if board[p.x][p.y] == Defines.BLACK else -Defines.WIN_SCORE
        if not empty_points(board):
            return 0
        if remaining == 0:
            return self.evaluate(board)
        moves = self.generate_moves(board, color, tactical_only=True)
        if not moves:
            if self.winning_completions(board, color ^ 3):
                # No own immediate win and no two-stone defence: the opponent
                # can finish next turn. This is not a static stand-pat choice.
                return -Defines.WIN_SCORE if color == Defines.BLACK else Defines.WIN_SCORE
            return self.evaluate(board)
        best = -float("inf") if color == Defines.BLACK else float("inf")
        for i, move in enumerate(moves):
            self.check_time()
            make_move(board, move, color)
            try:
                score = self.quiescence(board, color ^ 3, move, alpha, beta, remaining - 1)
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

    def alpha_beta(self, board, depth, color, previous_move, alpha=-float("inf"), beta=float("inf")):
        self.check_time()
        if depth == 0 and self.use_quiescence:
            return self.quiescence(board, color, previous_move, alpha, beta, Defines.Q_MAX_DEPTH)
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
        self.reset_stats()
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
