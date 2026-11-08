# tbe — version 1

Standalone baseline version for Practice 1, based on the teacher's five files.
Dependencies: Python 3 standard library only. Run with `python3 main.py`. For the GUI, select the executable `v1_baseline/main.py` in `tbe_gui`.

## Files

- `main.py`: engine entry point.
- `defines.py`: stone constants, move structure, and search parameters.
- `tools.py`: coordinates, making/undoing moves, win detection, and board printing.
- `game_engine.py`: protocol commands and responses.
- `search_engine.py`: local candidates, a simple evaluation, and minimax.

## Implementation

The 19×19 board is stored in a 21×21 array with a border, as in the starter code.
Black starts with one stone in the centre. Subsequent moves select pairs of
distinct empty cells; if only one empty cell remains, a one-stone move is allowed.
Six or more consecutive stones in any of the four directions constitute a win.
A full board without a winner is a draw. Restoring specified positions is supported.

Candidates are cells within a radius of **3** along each coordinate from any
stone on the board. The engine takes the 12 cells with the highest simple local
scores and up to 24 pairs. A pair is scored as the sum of its cell scores. This is
a deliberately restricted generator: minimax explores every proposed move, but
not every legal pair on the board. It can miss a strong move outside the selected list.

The static evaluation is the sum of black stone counts in unblocked windows
of length 6 minus the corresponding sum for white. A black win scores +1000000,
a white win −1000000, and a draw 0. This is a baseline heuristic without complex
threat patterns.

Minimax completes depths 1 and 2 full moves in sequence. When time runs out,
it returns the last completed result; a legal initial choice is available before
that. Temporary moves are always undone via `finally`.
A small part of the time budget is reserved for the response.

## Protocol

The response to `name` is `name tbe`. A computed move is returned as `move JJ`
or, for example, `move JKJL`. Coordinates use letters A–S and preserve the
starter code's orientation. A single stone may also be written as a repeated
pair, for example `JJJJ`.

- `new black`: start a new game and immediately make Black's first move, as in the starter code.
- `new white`: start a new game; a subsequent `move JJ` supplies the opponent's move and triggers a response.
- `new xxx`: reset for the GUI; `black/white XXXX` then restore the position,
  and `next` computes a move for the next colour.
- `move XXXX`: make the next player's move and compute a response.
- `depth 5`: set a budget of **5 seconds** per move, not the tree depth.
- `print`, `help`, `exit/quit`: print the board, show help, and exit.
- `vcf`, `unvcf`: accepted and ignored, as required by the assignment.

Protocol responses go to `stdout`. Search metrics and explicit input-command
errors go to `stderr`; the GUI does not parse them. No log file is created
automatically. A search command after the game has ended is explicitly rejected
without making another move.
