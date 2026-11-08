"""tbe v5: learn evaluation weights by search bootstrapping, then choose
between learned and manual weights with control games.

Run from connect6/tbe_engine:   python3 -B v5_final/train.py

1. Self-play: games from random openings. In every quiet position (no 4 or 5
   stones of one colour in any 6-window) a teacher search - one full turn plus
   quiescence, manual weights - gives the label.
2. Fit: the static evaluation is trained to predict the teacher score
   (logistic loss, Adam, early stopping on validation games).
3. Control: learned weights vs manual weights, each opening with both colours.
4. Choice: learned weights are kept if validation loss is lower AND they score
   more than 50 % in control games; otherwise manual weights are kept.
   The chosen weights are written to learned_weights.json.

--init naive: recovery experiment. Training starts from naive weights
(line_1..3 = 1, 2, 3, connectivity = 1) instead of the manual ones, and the
control games are learned vs these naive weights. It checks that the procedure
can find good weights by itself. learned_weights.json is NOT changed.
"""

import argparse
import csv
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import random
import statistics
import sys
import time
from datetime import datetime

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from defines import Defines, StoneMove
from search_engine import SearchEngine
from tools import empty_points, init_board, is_win_by_premove, make_move, move2msg, msg2move, unmake_move

MANUAL = dict(Defines.EVAL_WEIGHTS)
FEATURES = list(MANUAL)
FITTED = ['line_1', 'line_2', 'line_3', 'connectivity']   # the rest is zero in quiet positions
MAX_RATIO = {'line_1': 4.0, 'line_2': 4.0, 'line_3': 3.5, 'connectivity': 3.0}
MIN_RATIO = 0.25
NAIVE = dict(MANUAL, line_1=1, line_2=2, line_3=3, connectivity=1)

TURNS_PER_GAME = 40
EXPLORE_TURNS = 6        # random alternative moves only at the start of a game
EPSILON = 0.3
EPOCHS = 1500
PATIENCE = 120
LEARNING_RATE = 0.05
L2 = 0.001


# ---------------------------------------------------------------- openings

def new_board():
    board = [[0] * Defines.GRID_NUM for _ in range(Defines.GRID_NUM)]
    init_board(board)
    return board


def random_opening(rng):
    """Black stone near the centre, white pair, sometimes one more pair each."""
    board = new_board()
    x, y = 10 + rng.randint(-2, 2), 10 + rng.randint(-2, 2)
    first = StoneMove((x, y))
    make_move(board, first, Defines.BLACK)
    moves = [[Defines.BLACK, move2msg(first)]]
    stones = [(x, y)]
    plan = [(Defines.WHITE, 2)]
    if rng.random() < 0.6:
        plan.append((Defines.BLACK, 3))
        if rng.random() < 0.4:
            plan.append((Defines.WHITE, 3))
    for color, radius in plan:
        cells = sorted({(sx + dx, sy + dy) for sx, sy in stones
                        for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)
                        if 1 <= sx + dx <= 19 and 1 <= sy + dy <= 19 and board[sx + dx][sy + dy] == 0})
        a, b = rng.sample(cells, 2)
        move = StoneMove(a, b)
        make_move(board, move, color)
        moves.append([color, move2msg(move)])
        stones += [a, b]
    return moves


def opening_board(moves):
    board = new_board()
    for color, text in moves:
        make_move(board, msg2move(text), color)
    return board, moves[-1][0] ^ 3


# ---------------------------------------------------------------- 1. self-play

def teacher_search(engine, board, color):
    """Exact value of one full turn + quiescence (black-positive), and the best move."""
    engine.deadline = None
    moves = engine.generate_moves(board, color)
    best, best_move = None, None
    for move in moves:
        make_move(board, move, color)
        score = engine.alpha_beta(board, 0, color ^ 3, move)
        unmake_move(board, move)
        if best is None or (score > best if color == Defines.BLACK else score < best):
            best, best_move = score, move
    return best, best_move, moves


def selfplay(task):
    worker, seed, deadline = task
    rng = random.Random(seed)
    engine = SearchEngine(weights=MANUAL)
    rows, games = [], 0
    while time.time() < deadline:
        board, color = opening_board(random_opening(rng))
        game = f'w{worker}g{games}'
        games += 1
        for turn in range(TURNS_PER_GAME):
            if time.time() >= deadline or not empty_points(board):
                break
            score, move, moves = teacher_search(engine, board, color)
            black, white, _ = engine.analyse_position(board)
            quiet = all(black[n] == 0 and white[n] == 0 for n in ('line_4', 'line_5'))
            if quiet and abs(score) < Defines.WIN_SCORE / 2:
                rows.append({'game': game, 'to_move': color, 'teacher': score,
                             'features': {n: black[n] - white[n] for n in FEATURES}})
            if turn < EXPLORE_TURNS and len(moves) > 1 and rng.random() < EPSILON:
                move = rng.choice(moves[1:4])
            make_move(board, move, color)
            if is_win_by_premove(board, move):
                break
            color ^= 3
    return rows, games


# ---------------------------------------------------------------- 2. fit

def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    return math.exp(z) / (1 + math.exp(z))


def log_loss(z, y):
    return max(z, 0) - z * y + math.log1p(math.exp(-abs(z)))


def lower_bound(name, start):
    return min(MANUAL[name] * MIN_RATIO, start[name])


def to_weights(params):
    w = dict(MANUAL)
    for name, p in zip(FITTED, params):
        w[name] = MANUAL[name] * math.exp(p)
    return w


def clamp(params, start):
    """Bounds around the manual weights and line_1 < line_2 < line_3 < line_4."""
    w = to_weights(params)
    for name in FITTED:
        w[name] = min(max(w[name], lower_bound(name, start)), MANUAL[name] * MAX_RATIO[name])
    for prev, name in [('line_1', 'line_2'), ('line_2', 'line_3')]:
        w[name] = min(max(w[name], w[prev] * 1.1), MANUAL[name] * MAX_RATIO[name])
    return [math.log(w[name] / MANUAL[name]) for name in FITTED]


def make_dataset(rows, k):
    """Each row: fixed part of z, fitted parts of z, tempo sign, target in 0..1."""
    data = []
    for r in rows:
        f = r['features']
        fixed = sum(MANUAL[n] * f[n] for n in FEATURES if n not in FITTED) / k
        parts = [MANUAL[n] * f[n] / k for n in FITTED]
        tempo = 1 if r['to_move'] == Defines.BLACK else -1
        data.append((fixed, parts, tempo, sigmoid(r['teacher'] / k)))
    return data


def loss_and_grad(data, params, c):
    ratios = [math.exp(p) for p in params]
    loss, grad, grad_c = 0.0, [0.0] * len(params), 0.0
    for fixed, parts, tempo, y in data:
        terms = [v * r for v, r in zip(parts, ratios)]
        z = fixed + sum(terms) + c * tempo
        loss += log_loss(z, y)
        residual = sigmoid(z) - y
        for i, t in enumerate(terms):
            grad[i] += residual * t
        grad_c += residual * tempo
    n = len(data)
    return loss / n, [g / n for g in grad], grad_c / n


def adam(train, val, fit_weights, name, history, start):
    """Starts from the start weights. fit_weights=False: only the tempo term c (baseline)."""
    p0 = [math.log(start[n] / MANUAL[n]) for n in FITTED]
    params, c = p0[:], 0.0
    m, v = [0.0] * (len(FITTED) + 1), [0.0] * (len(FITTED) + 1)
    best, stale = None, 0
    for epoch in range(1, EPOCHS + 1):
        _, grad, grad_c = loss_and_grad(train, params, c)
        if fit_weights:
            grad = [g + 2 * L2 * (p - q) for g, p, q in zip(grad, params, p0)]   # L2 towards the start
        else:
            grad = [0.0] * len(FITTED)
        values = params + [c]
        for i, g in enumerate(grad + [grad_c]):
            m[i] = 0.9 * m[i] + 0.1 * g
            v[i] = 0.999 * v[i] + 0.001 * g * g
            values[i] -= LEARNING_RATE * (m[i] / (1 - 0.9 ** epoch)) / (math.sqrt(v[i] / (1 - 0.999 ** epoch)) + 1e-8)
        params, c = (clamp(values[:-1], start) if fit_weights else params), values[-1]
        if epoch % 5 == 0:
            train_loss = loss_and_grad(train, params, c)[0]
            val_loss = loss_and_grad(val, params, c)[0]
            w = to_weights(params)
            history.append([name, epoch, train_loss, val_loss] + [w[n] for n in FITTED])
            if best is None or val_loss < best['val_loss'] - 1e-7:
                best = {'epoch': epoch, 'train_loss': train_loss, 'val_loss': val_loss, 'params': params}
                stale = 0
            else:
                stale += 5
                if stale >= PATIENCE:
                    break
    return best


# ---------------------------------------------------------------- 3. control games

def control_game(task):
    opening, learned_color, learned, opponent, move_seconds, deadline = task
    board, color = opening_board(opening)
    engines = {learned_color: SearchEngine(weights=learned),
               learned_color ^ 3: SearchEngine(weights=opponent)}
    for _ in range(TURNS_PER_GAME):
        if time.time() + move_seconds > deadline:
            return None                       # not finished: not counted
        if not empty_points(board):
            return 0.5
        move = engines[color].choose_move(board, color, move_seconds)
        make_move(board, move, color)
        if is_win_by_premove(board, move):
            return 1.0 if color == learned_color else 0.0
        color ^= 3
    return 0.5                                # turn limit counted as a draw


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--minutes', type=float, default=30)
    parser.add_argument('--workers', type=int, default=max(1, min(6, os.cpu_count() - 2)))
    parser.add_argument('--move-seconds', type=float, default=3.0)
    parser.add_argument('--control-openings', type=int, default=12)
    parser.add_argument('--seed', type=int, default=20261107)
    parser.add_argument('--init', choices=['manual', 'naive'], default='manual')
    args = parser.parse_args()
    start_weights = MANUAL if args.init == 'manual' else NAIVE

    start = time.time()
    budget = min(args.minutes, 30) * 60
    run = HERE / 'training_runs' / (f'run_{args.init}_' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    run.mkdir(parents=True)
    pool = mp.get_context('spawn').Pool(args.workers)
    print('Results:', run)

    # 1. self-play data
    print(f'[1/4] self-play for {0.5 * budget / 60:.1f} min with {args.workers} processes')
    tasks = [(w, args.seed * 100 + w, start + 0.5 * budget) for w in range(args.workers)]
    outputs = pool.map(selfplay, tasks)
    rows = [r for worker_rows, _ in outputs for r in worker_rows]
    games = sum(n for _, n in outputs)
    with open(run / 'positions.jsonl', 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    print(f'      {games} games, {len(rows)} labelled quiet positions')

    # 2. fit (train/validation split by game)
    names = sorted({r['game'] for r in rows})
    random.Random(args.seed).shuffle(names)
    val_games = set(names[:len(names) // 5])
    train_rows = [r for r in rows if r['game'] not in val_games]
    val_rows = [r for r in rows if r['game'] in val_games]
    k = statistics.median(abs(r['teacher']) for r in train_rows if r['teacher'] != 0)
    train, val = make_dataset(train_rows, k), make_dataset(val_rows, k)
    history = []
    baseline = adam(train, val, False, 'start', history, start_weights)
    fitted = adam(train, val, True, 'learned', history, start_weights)
    learned = to_weights(fitted['params'])
    learned = {n: round(w, 3) if n in FITTED else w for n, w in learned.items()}
    with open(run / 'history.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['run', 'epoch', 'train_loss', 'val_loss'] + FITTED)
        writer.writerows(history)
    print(f'[2/4] train/val positions {len(train_rows)}/{len(val_rows)}, scale K = {k:.1f}')
    print(f"      val loss: {args.init} start {baseline['val_loss']:.5f}, learned {fitted['val_loss']:.5f}")
    print('      learned weights:', {n: learned[n] for n in FITTED})

    # 3. control games learned vs manual
    print(f'[3/4] control games learned vs {args.init} weights')
    rng = random.Random(args.seed + 1)
    openings = [random_opening(rng) for _ in range(args.control_openings)]
    tasks = [(o, color, learned, start_weights, args.move_seconds, start + budget - 20)
             for o in openings for color in (Defines.BLACK, Defines.WHITE)]
    scores = [s for s in pool.map(control_game, tasks) if s is not None]
    pool.close()
    score = sum(scores) / len(scores) if scores else 0
    print(f'      learned: {scores.count(1.0)} wins, {scores.count(0.0)} losses, '
          f'{scores.count(0.5)} draws of {len(scores)} finished games -> {score:.1%}')

    # 4. choice (only in the normal run; the naive run is an experiment)
    accepted = fitted['val_loss'] < baseline['val_loss'] and len(scores) >= len(tasks) // 2 and score > 0.5
    chosen = learned if accepted else start_weights
    source = 'learned' if accepted else args.init
    if args.init == 'manual':
        with open(HERE / 'learned_weights.json', 'w') as f:
            json.dump({'engine': 'tbe', 'version': 5, 'source': source, 'weights': chosen}, f, indent=2)
    result = {
        'init': args.init, 'start_weights': start_weights,
        'selfplay_games': games, 'labelled_positions': len(rows),
        'train_positions': len(train_rows), 'val_positions': len(val_rows), 'scale_k': k,
        'start_train_loss': baseline['train_loss'], 'start_val_loss': baseline['val_loss'],
        'learned_train_loss': fitted['train_loss'], 'learned_val_loss': fitted['val_loss'],
        'best_epoch': fitted['epoch'],
        'control_games': len(scores), 'control_wins': scores.count(1.0),
        'control_losses': scores.count(0.0), 'control_draws': scores.count(0.5), 'control_score': score,
        'manual_weights': MANUAL, 'learned_weights': learned, 'chosen': source, 'chosen_weights': chosen,
        'minutes': (time.time() - start) / 60,
    }
    with open(run / 'result.json', 'w') as f:
        json.dump(result, f, indent=2)
    if args.init == 'manual':
        print(f'[4/4] chosen: {source} weights -> learned_weights.json')
    else:
        print(f'[4/4] naive experiment: learned weights would be {"kept" if accepted else "rejected"}; '
              'learned_weights.json not changed')


if __name__ == '__main__':
    main()
