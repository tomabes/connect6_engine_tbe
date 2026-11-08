# tbe — version 2

An improved copy of `v1_baseline`. `tools.py` and `game_engine.py` were
copied unchanged; only the version comment was changed in `main.py`.
New parameters were added to `defines.py`; the main changes are in
`search_engine.py`.

## Inherited from v1

Five files, a 21×21 array containing a 19×19 playing board, coordinates A–S,
the name `tbe`, and the entire command protocol. The local candidate radius is
always **3**. The normal pool contains 12 cells and up to 24 pairs. The maximum
depth remains **2 full moves**; depths 1 and 2 are completed in sequence.
`depth 5` sets 5 seconds per move. Timer checks and undoing temporary moves
via `finally` are preserved.

## Second-stage changes

### Alpha-beta

The `alpha_beta` method follows the structure of `minimax` in v1: terminal
positions, the depth limit, maximisation for black, and minimisation for white
are unchanged. Bounds `alpha` and `beta` are added; when `alpha >= beta`, the
remaining moves at that node are not explored. The root passes the improved
bound to subsequent branches.

### Improved candidates and move ordering

Cells are ranked by their ability to strengthen friendly unblocked lines and
interfere with the opponent's lines. In a normal position, a pair is scored by
the joint change in the affected windows of length 6. This accounts for the
two stones potentially strengthening the same line; v1 added the independent
scores of the two cells.

If an immediate win exists, moves that complete it are proposed. Otherwise,
unblocked opponent windows containing four or five stones are checked.
A defensive pair must block ALL such ways of winning in one move.
Critical cells are included in these pairs regardless of the normal 12-cell
limit; geometrically, they still lie within the local radius-3 area.
If no two-stone defence exists, the engine continues searching legal moves
to evaluate the loss and does not declare a partial defence successful.

Windows sharing an empty cell are not counted as independent threats. They
are used as win/defence conditions.

### Improved evaluation

The linear stone count from v1 is replaced with manual weights:

| Stones of one colour in an unblocked window | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Weight | 1 | 4 | 16 | 64 | 256 |

The score is black's evaluation minus white's; mixed windows contribute 0.
A win scores +1000000 for black and −1000000 for white; a draw scores 0.
Even the upper bound on the sum of ordinary weights is smaller than the
absolute win score. This is a manual heuristic.

## Running

Run `python3 main.py`, or select the executable `v2_alpha_beta/main.py` in the GUI.
The engine name remains `tbe`. Commands `new black`,
`new white`, `new xxx`, `black`, `white`, `next`, `move`, `name`, `depth`,
`print`, `help`, `vcf/unvcf`, and `exit/quit` work as in v1.
Protocol responses go to stdout; metrics go to stderr.

## Metrics and checks

- `nodes`: number of visited search nodes, including leaves.
- `pruned`: number of immediate child moves skipped at cutoff nodes.
- `cutoffs`: number of cutoffs that actually skipped at least one move.
- `depth_reached`: last fully completed depth.
- `timed_out`, `seconds`: budget exhaustion and search time, including move generation.
