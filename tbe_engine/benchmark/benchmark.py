"""Experiments for the report: test positions and a tournament.

Run from connect6/tbe_engine:   python3 -B benchmark/benchmark.py

1. Test positions, every version v1..v5 against Cloudict (guide, session 5):
     win in 1 / 2 / 3 turns     the engine must win within that many own turns
     defend 1 / 2 / 3 turns     the opponent threatens to win in that many turns;
                                the engine must not lose during 4 own turns
     start                      normal opening; how long the engine survives
   Each category has 2 positions: the same pattern for black and, rotated,
   for white. Search metrics (time, nodes, pruned, depth) are taken from the
   engine's FIRST move, so all versions are measured on identical positions.
2. Tournament: v1..v5 and Cloudict, every pair, 2 openings, both colours.

No time limit by default: every test and game is played to the end
(expected 30-45 minutes). --minutes N stops starting new moves after N minutes.

Results in benchmark/results_DATE-TIME/: battery.csv, first_moves.csv,
tournament.csv, tables.txt and metrics.png.

Ablation of v4:   python3 -B benchmark/benchmark.py --ablation
   only the test positions (no tournament), for v4 in four modes: without both
   optimisations (v4_base), quiescence only (v4_QS), forward pruning only (v4_FP)
   and both (v4_QS+FP = normal v4). Results in benchmark/ablation_DATE-TIME/.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ENGINE_DIR = Path(__file__).resolve().parent.parent          # connect6/tbe_engine
PROJECT = ENGINE_DIR.parent                                   # connect6
sys.path.insert(0, str(ENGINE_DIR / 'v5_final'))
sys.path.append(str(PROJECT / 'tbe_gui'))

from tools import empty_points, init_board, is_win_by_premove, make_move, msg2move
from engine_process import EngineError, EngineProcess

VERSIONS = {'v1': 'v1_baseline', 'v2': 'v2_alpha_beta', 'v3': 'v3_threat_evaluation',
            'v4': 'v4_search_optimisations', 'v5': 'v5_final'}
# Ablation of v4 (--ablation): the same engine with quiescence (QS) and forward
# pruning (FP) switched on/off by the command-line flags of v4_search_optimisations/main.py.
ABLATION = {'v4_base': ('v4_search_optimisations', ['--no-quiescence', '--no-forward-pruning']),
            'v4_QS':   ('v4_search_optimisations', ['--no-forward-pruning']),
            'v4_FP':   ('v4_search_optimisations', ['--no-quiescence']),
            'v4_QS+FP': ('v4_search_optimisations', [])}
# name -> (folder, extra arguments); every name from VERSIONS and ABLATION
ENGINES = {**{n: (f, []) for n, f in VERSIONS.items()}, **ABLATION}
CLOUDICT = PROJECT / 'tbe_gui' / 'engines' / 'cloudict_native'
PATTERNS = PROJECT / 'tbe_gui' / 'engines' / 'patterns.in'
BLACK, WHITE = 1, 2


# ---------------------------------------------------------------- positions
# Cells are (column, row) with 1..19 = letters A..S, as in the GUI text "CR".

def cell(c, r):
    return chr(64 + c) + chr(64 + r)


def rotate(cells):
    return [(20 - r, c) for c, r in cells]


# Far-away stones on the edges (at least 6 apart): only used to make the stone
# counts of a test position legal (black 1 + 2 + 2 ..., white 2 + 2 ...).
FILLERS = [(1, 1), (19, 19), (7, 1), (13, 19), (13, 1), (7, 19), (19, 1), (1, 19),
           (1, 7), (19, 13), (1, 13), (19, 7)]

# attacker stones, defender stones
PATTERNS_BY_CATEGORY = {
    # four in a row with free ends: two more stones make six
    'win1': ([(6, 10), (7, 10), (8, 10), (9, 10)], [(8, 12), (12, 8), (5, 14)]),
    # two separate open threes: one stone each -> two open fours -> 4 blocks needed
    'win2': ([(7, 6), (8, 6), (9, 6), (14, 11), (14, 12), (14, 13)], [(10, 10), (4, 14), (11, 15)]),
    # open three + two open twos crossing at (10, 13):
    # turn 1 open four (opponent must use both stones) + crossing stone (two threes),
    # turn 2 two open fours, turn 3 six
    'win3': ([(5, 4), (6, 4), (7, 4), (11, 13), (12, 13), (10, 14), (10, 15)],
             [(15, 7), (4, 9), (16, 16)]),
}


def history_for(own, other, own_color):
    """Legal-looking move history with `own_color` to move next."""
    stones = {own_color: [cell(c, r) for c, r in own], own_color ^ 3: [cell(c, r) for c, r in other]}
    n = 1
    while True:
        need = {BLACK: 2 * n - 1, WHITE: 2 * n} if own_color == BLACK else {BLACK: 2 * n + 1, WHITE: 2 * n}
        if need[BLACK] >= len(stones[BLACK]) and need[WHITE] >= len(stones[WHITE]):
            break
        n += 1
    fillers = [cell(c, r) for c, r in FILLERS]
    for color in (BLACK, WHITE):
        while len(stones[color]) < need[color]:
            stones[color].append(fillers.pop(0))
    history = [[BLACK, stones[BLACK].pop(0)]]
    color = WHITE
    while stones[BLACK] or stones[WHITE]:
        history.append([color, stones[color].pop(0) + stones[color].pop(0)])
        color ^= 3
    return history


def test_positions():
    """(name, category, engine colour, history, max engine turns)."""
    tests = []
    for category, (attack, defence) in PATTERNS_BY_CATEGORY.items():
        turns = int(category[-1])
        for color, a, d in ((BLACK, attack, defence), (WHITE, rotate(attack), rotate(defence))):
            tests.append((f'{category}_{"black" if color == BLACK else "white"}', category, color,
                          history_for(a, d, color), turns))
            # same pattern for the opponent, engine to move: it has to defend
            tests.append((f'defend{turns}_{"black" if color == BLACK else "white"}', f'defend{turns}',
                          color ^ 3, history_for(d, a, color ^ 3), 4))
    tests.append(('start_white', 'start', WHITE, [[BLACK, 'JJ']], 15))
    tests.append(('start_black', 'start', BLACK, [[BLACK, 'JJ'], [WHITE, 'IKKK']], 15))
    return tests


TOURNAMENT_OPENINGS = {'opening_1': [[BLACK, 'JJ'], [WHITE, 'KJKK']],
                       'opening_2': [[BLACK, 'JJ'], [WHITE, 'HHLL']]}


# ---------------------------------------------------------------- playing

def start_engine(name, move_seconds, cloudict_depth, folder):
    if name == 'cloudict':
        engine = EngineProcess([str(CLOUDICT)], cwd=folder)
    else:
        folder_name, extra = ENGINES[name]
        engine = EngineProcess([sys.executable, '-B', str(ENGINE_DIR / folder_name / 'main.py')] + extra)
    # Cloudict prints its help at start-up, including the line "move XXXX - tell the
    # engine ...". Waiting for the answer to "name" skips everything printed before.
    engine.send('name')
    engine.expect('name ', timeout=10)
    if name == 'cloudict':
        engine.send(f'depth {cloudict_depth}')
        engine.send('vcf')
    else:
        engine.send(f'depth {move_seconds}')
    return engine


def ask_move(engine, history, timeout):
    """Send the whole position, return (move text, metrics dict or None)."""
    seen = sum(line.startswith('metrics') for line in engine.stderr)
    commands = ['new xxx'] + [('black ' if c == BLACK else 'white ') + (t * 2 if len(t) == 2 else t)
                              for c, t in history] + ['next']
    engine.send('\n'.join(commands))
    end = time.time() + timeout
    while True:
        line = engine.readline(end - time.time()).strip()
        if line.startswith('move '):
            break
    metrics = None
    for _ in range(50):                      # stderr is read by another thread
        lines = [l for l in engine.stderr if l.startswith('metrics')]
        if len(lines) > seen:
            metrics = json.loads(lines[-1][len('metrics '):])
            break
        time.sleep(0.01)
    return line[5:], metrics


def play(players, history, max_turns, move_seconds, cloudict_depth, deadline, count_color=None):
    """players: {colour: name}. max_turns counts turns of count_color (or all turns).
    Returns winner (1, 2, 0 = full board, None = stopped), reason, moves."""
    history = [list(h) for h in history]
    board = [[0] * 21 for _ in range(21)]
    init_board(board)
    for color, text in history:
        make_move(board, msg2move(text), color)
    color = history[-1][0] ^ 3
    moves, counted = [], 0
    with tempfile.TemporaryDirectory() as folder:
        shutil.copy(PATTERNS, Path(folder) / 'patterns.in')    # Cloudict reads it from cwd
        engines = {c: start_engine(n, move_seconds, cloudict_depth, folder) for c, n in players.items()}
        winner, reason = None, 'turn_limit'
        try:
            while counted < max_turns:
                if time.time() + move_seconds > deadline:
                    reason = 'budget'
                    break
                if not empty_points(board):
                    winner, reason = 0, 'full_board'
                    break
                timeout = 30 if players[color] == 'cloudict' else move_seconds + 10
                text, metrics = ask_move(engines[color], history, timeout)
                move = msg2move(text)
                make_move(board, move, color)
                history.append([color, text])
                moves.append({'color': color, 'player': players[color], 'move': text, 'metrics': metrics})
                if count_color is None or color == count_color:
                    counted += 1
                if is_win_by_premove(board, move):
                    winner, reason = color, 'six'
                    break
                color ^= 3
        except (TimeoutError, EngineError, ValueError) as error:    # no answer / crash / illegal move
            winner, reason = color ^ 3, f'{players[color]} failed: {error}'
        for engine in engines.values():
            engine.close()
    return winner, reason, moves


# ---------------------------------------------------------------- tasks

def run_test(task):
    version, (name, category, color, history, turns), args, deadline = task
    winner, reason, moves = play({color: version, color ^ 3: 'cloudict'}, history, turns,
                                 args.move_seconds, args.cloudict_depth, deadline, count_color=color)
    own = [m for m in moves if m['color'] == color]
    if category.startswith('win'):
        result = 'pass' if winner == color else 'fail'
    elif category.startswith('defend'):
        result = 'fail' if winner == color ^ 3 else 'pass'
    else:
        result = {color: 'win', color ^ 3: 'loss', 0: 'draw'}.get(winner, 'no result')
    if reason == 'budget':
        result = 'not played'
    first = own[0]['metrics'] if own and own[0]['metrics'] else {}
    print(f'  {version} {name}: {result} ({reason}, {len(own)} own turns)', flush=True)
    return {'version': version, 'test': name, 'category': category, 'engine_color': color,
            'result': result, 'reason': reason, 'own_turns': len(own),
            'first_seconds': first.get('seconds'), 'first_nodes': first.get('nodes'),
            'first_pruned': first.get('pruned'), 'first_depth': first.get('depth_reached'),
            # v4 metrics (absent in v1..v3): quiescence nodes, forward-pruned pairs, time-out
            'first_q_nodes': first.get('q_nodes'), 'first_forward_pruned': first.get('forward_pruned'),
            'first_timed_out': first.get('timed_out')}


def run_game(task):
    black, white, opening, args, deadline = task
    winner, reason, moves = play({BLACK: black, WHITE: white}, TOURNAMENT_OPENINGS[opening], 30,
                                 args.move_seconds, args.cloudict_depth, deadline)
    print(f'  {black} (black) vs {white} (white), {opening}: winner '
          f'{ {BLACK: black, WHITE: white, 0: "draw"}.get(winner, "-") } ({reason})', flush=True)
    return {'black': black, 'white': white, 'opening': opening, 'winner': winner,
            'reason': reason, 'turns': len(moves)}


# ---------------------------------------------------------------- report

def average(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else float('nan')


def tables(battery, tournament, versions=VERSIONS):
    """versions: engine names shown as columns; tournament=None skips the tournament table."""
    w = max(8, max(len(v) for v in versions) + 2)            # column width
    out = ['Test positions against Cloudict (passed / played)', '']
    categories = ['win1', 'win2', 'win3', 'defend1', 'defend2', 'defend3']
    out.append(f"{'category':<10}" + ''.join(f'{v:>{w}}' for v in versions))
    for category in categories:
        row = f'{category:<10}'
        for v in versions:
            rows = [b for b in battery if b['version'] == v and b['category'] == category and b['result'] != 'not played']
            row += f"{sum(b['result'] == 'pass' for b in rows)}/{len(rows)}".rjust(w)
        out.append(row)
    row = f"{'start':<10}"
    for v in versions:
        rows = [b for b in battery if b['version'] == v and b['category'] == 'start']
        row += f"{average([b['own_turns'] for b in rows]):>{w}.1f}"
    out.append(row + '   (average own turns before the game ended or 15)')
    out += ['', 'First-move search metrics on the same 14 positions (average)', '',
            f"{'version':<10}{'seconds':>10}{'nodes':>10}{'pruned':>10}{'depth':>8}"
            f"{'q_nodes':>10}{'fwd_pruned':>12}{'timeouts':>10}"]
    for v in versions:
        rows = [b for b in battery if b['version'] == v]
        out.append(f"{v:<10}{average([b['first_seconds'] for b in rows]):>10.2f}"
                   f"{average([b['first_nodes'] for b in rows]):>10.0f}"
                   f"{average([b['first_pruned'] for b in rows]):>10.0f}"
                   f"{average([b['first_depth'] for b in rows]):>8.2f}"
                   f"{average([b.get('first_q_nodes') for b in rows]):>10.0f}"
                   f"{average([b.get('first_forward_pruned') for b in rows]):>12.0f}"
                   f"{sum(bool(b.get('first_timed_out')) for b in rows):>10}")
    if tournament is None:
        return '\n'.join(out)
    out += ['', 'Tournament (win 1, draw 0.5; unfinished games not counted)', '',
            f"{'player':<10}{'points':>8}{'wins':>6}{'losses':>8}{'draws':>7}{'games':>7}"]
    players = list(VERSIONS) + ['cloudict']
    standings = []
    for p in players:
        games = [g for g in tournament if p in (g['black'], g['white']) and g['winner'] is not None]
        wins = sum((g['winner'] == BLACK and g['black'] == p) or (g['winner'] == WHITE and g['white'] == p) for g in games)
        draws = sum(g['winner'] == 0 for g in games)
        standings.append((wins + 0.5 * draws, p, wins, len(games) - wins - draws, draws, len(games)))
    for points, p, wins, losses, draws, n in sorted(standings, reverse=True):
        out.append(f'{p:<10}{points:>8.1f}{wins:>6}{losses:>8}{draws:>7}{n:>7}')
    return '\n'.join(out)


def plot(battery, path, versions=VERSIONS):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    versions = list(versions)
    nodes = [average([b['first_nodes'] for b in battery if b['version'] == v]) for v in versions]
    pruned = [average([b['first_pruned'] for b in battery if b['version'] == v]) for v in versions]
    seconds = [average([b['first_seconds'] for b in battery if b['version'] == v]) for v in versions]
    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4))
    x = range(len(versions))
    left.bar([i - 0.2 for i in x], nodes, width=0.38, color='#2a78d6', label='expanded nodes')
    left.bar([i + 0.2 for i in x], pruned, width=0.38, color='#eb6834', label='pruned successors')
    left.set_xticks(list(x), versions)
    left.set_title('Search size, first move (average)', loc='left')
    left.legend(frameon=False)
    right.bar(list(x), seconds, width=0.5, color='#1baf7a')
    right.set_xticks(list(x), versions)
    right.set_ylabel('seconds')
    right.set_title('Decision time, first move (average)', loc='left')
    for ax in (left, right):
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', color='#e4e3df')
        ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=200)


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--minutes', type=float, default=0, help='0 = no limit')
    parser.add_argument('--move-seconds', type=float, default=3.0)
    parser.add_argument('--cloudict-depth', type=int, default=2)
    parser.add_argument('--workers', type=int, default=5)
    parser.add_argument('--ablation', action='store_true',
                        help='only the test positions, for v4 with QS / FP on and off (no tournament)')
    args = parser.parse_args()
    start = time.time()
    deadline = start + args.minutes * 60 if args.minutes > 0 else float('inf')
    prefix = 'ablation_' if args.ablation else 'results_'
    out = Path(__file__).resolve().parent / (prefix + datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir()
    print('Results:', out)
    versions = list(ABLATION) if args.ablation else list(VERSIONS)

    tests = test_positions()
    with open(out / 'positions.json', 'w') as f:
        json.dump([{'name': t[0], 'category': t[1], 'engine_color': t[2], 'history': t[3]} for t in tests], f, indent=1)

    print(f'[1/2] {len(tests)} test positions x {len(versions)} versions against Cloudict')
    tasks = [(v, t, args, deadline) for t in tests for v in versions]
    with ThreadPoolExecutor(args.workers) as pool:
        battery = list(pool.map(run_test, tasks))
    with open(out / 'battery.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(battery[0]))
        writer.writeheader()
        writer.writerows(battery)

    if args.ablation:
        text = tables(battery, None, versions)
        (out / 'tables.txt').write_text(text + '\n')
        plot(battery, out / 'metrics.png', versions)
        print()
        print(text)
        print(f'\nDone in {(time.time() - start) / 60:.1f} min. Saved in {out}')
        return

    print('[2/2] tournament')
    players = list(VERSIONS) + ['cloudict']
    games = [(black, white, o, args, deadline) for i, a in enumerate(players) for b in players[i + 1:]
             for o in TOURNAMENT_OPENINGS for black, white in ((a, b), (b, a))]
    with ThreadPoolExecutor(args.workers) as pool:
        tournament = list(pool.map(run_game, games))
    with open(out / 'tournament.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(tournament[0]))
        writer.writeheader()
        writer.writerows(tournament)

    text = tables(battery, tournament)
    (out / 'tables.txt').write_text(text + '\n')
    plot(battery, out / 'metrics.png')
    print()
    print(text)
    print(f'\nDone in {(time.time() - start) / 60:.1f} min. Saved in {out}')


if __name__ == '__main__':
    main()
