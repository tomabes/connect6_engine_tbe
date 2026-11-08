# tbe — version 4

This folder was copied from `v3_threat_evaluation`. Two selected search
optimisations were added: **quiescence search** and additional **forward pruning**.
They can be enabled independently so that the fifth part of the project can
measure the contribution of each technique and their combination.

## Continuity

The five original files, the 19×19 board with a border, candidate radius **3**,
normal depth of **2 full moves**, and time limit are preserved. `tools.py`,
the nine evaluation features, their manual weights, `analyse_position`,
`feature_score`, `evaluate`, and the main pair-scoring order are inherited from v3.

Candidate generation and handling of the depth limit were changed in
`search_engine.py`. A `search_engine` parameter was added to `game_engine.py`
so that `main.py` can pass the selected settings. The GUI text commands and
response format are preserved.

## Quiescence search

When normal alpha-beta reaches depth 0, a limited tactical continuation is
performed instead of an immediate static evaluation:

1. If six in a row already exists or the board is full, return the terminal result.
2. If the limit `Q_MAX_DEPTH = 1` has been reached, return the v3 static evaluation.
3. Consider own wins in one move first. If none exists, consider mandatory
   defences against the opponent's wins in one move.
4. In a quiet position without such threats, return the existing evaluation
   immediately. Normal pairs are not generated or ranked for this purpose.
5. Under an immediate threat, doing nothing and retaining the static
   evaluation (stand pat) is not allowed: defensive variations must be explored.
6. If there is no own immediate win and no pair defends against all of the
   opponent's immediate wins, return a loss score. The check uses the exact
   six-cell window completion conditions from v3.

In critical branches, the depth can reach two normal moves plus one tactical
move. Other branches retain the previous depth. The extension is bounded by
both depth and the overall timer. Alpha-beta is used; every temporary placement
is undone via `finally`, including on timeout.
This is limited quiescence search over immediate threats.

### Adjustment after manual testing

Initially, two additional tactical moves were allowed. In a manual game,
this exhausted the 4-second budget and returned a result from normal depth 1.
The issue was reproduced on two specified opening positions: a quiescence
limit of 2 caused a timeout, whereas a limit of 1 allowed normal depth 2 to
complete. Depth 2 also completed on two other test positions; the selected
moves matched in all four examples. Only `Q_MAX_DEPTH` was changed;
the evaluation, candidates, forward pruning, and mandatory-defence checks
were preserved.

## Additional forward pruning

The local-area and move-list restrictions already existed in v1–v3. V4
examines additional selection within the same local space:

- After generation and deduplication, normal pairs are first scored using
  the inexpensive change in the affected six-cell windows (the v2 local-evaluation idea).
- Up to `FP_PRESELECT = 24` normal pairs are retained before the expensive
  v3 threat and connectivity analysis. This reduces the cost of generation itself.
- After full ranking, up to `FP_MAX_QUIET_MOVES = 8` quiet pairs are retained.
  Forcing pairs found among the preselected pairs are not removed by this limit.
  The previous overall limit of 24 pairs remains.
- If an own immediate win or an immediate opponent threat exists, both
  additional restrictions are bypassed. These positions retain the existing
  v3 critical-move generator.

Forward pruning is heuristic: preselection can lose a promising strategic
move or a move that creates a future forcing sequence. Preserving immediate
wins and defences does not guarantee the globally best move. The experimental
part therefore compares not only speed and node counts, but also the
solutions found in tactical positions.

## Four independent modes

Both techniques are enabled by default. In the GUI, select the executable
`v4_search_optimisations/main.py`.

Run from the version folder:

| Mode | Command |
|---|---|
| Baseline, both disabled | `python3 main.py --no-quiescence --no-forward-pruning` |
| Quiescence only | `python3 main.py --no-forward-pruning` |
| Forward pruning only | `python3 main.py --no-quiescence` |
| Both enabled | `python3 main.py` |

The same settings are available to the experimental script:
`SearchEngine(use_quiescence=..., use_forward_pruning=...)`.
With both disabled, the v3 candidates, evaluation, and normal search horizon
are preserved.

## Metrics

- `nodes`: all visited alpha-beta and quiescence nodes, including leaves;
  the shared boundary between them is not counted twice.
- `pruned`, `cutoffs`: immediate child moves skipped and the number of
  alpha-beta cutoffs; these include the tactical continuation.
- `forward_pruned`: number of candidate pairs removed by the additional
  preselection and quiet-pair limit. Counted separately from alpha-beta pruning.
- `q_nodes`: quiescence calls, including quiet leaves without an extension.
- `q_depth_reached`: maximum additional depth actually visited;
  0 means no additional moves. This is the maximum over the visited search,
  which may have been interrupted by the timer, not necessarily a completed iteration.
- `depth_reached`: last fully completed normal depth, 1 or 2.
- `quiescence`, `forward_pruning`: settings for the current run.
- `timed_out`, `seconds`: budget exhaustion and search time, including move generation.
