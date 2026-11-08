# tbe — version 3

Based on `v2_alpha_beta`. The five files and the same GUI interaction scheme
are preserved. `game_engine.py` and `tools.py` are the same as in v2;
`alpha_beta` and time management are also retained. The main changes concern
position features and the move-generation order in `search_engine.py`.

## Third stage of the assignment and sources

The task is to study approaches to Connect6, improve the detection of imminent
threats, and design an evaluation function as a weighted sum.
V2 already checked for immediate wins and defences; v3 preserves these checks
and adds an evaluation of future threat strength and connectivity.

1. **I-Chen Wu, Dei-Yen Huang, A New Family of k-in-a-row Games**, sections 4.1
   and 4.3 (`A_New_Family_of_k-in-a-Row_Games-2.pdf`).
   A threat is defined by the number of stones needed to defend against it.
   Overlapping windows cannot automatically be treated as independent. When
   generating a pair, the second cell must be re-evaluated after placing the first stone.
2. **Liu Yung-ching, A Defensive Strategy Combined with Threat-Space Search
   for Connect6**, sections 3.2.1–3.2.3 (`Original-Thesis-Liu_Yung_ching.pdf`).
   Key ideas are potential six-cell lines, influence decreasing with distance,
   and influence stopping at a boundary or an opponent's stone. V3 adapts these
   ideas into a simple connectivity feature; the thesis's original
   multiplicative formula is not implemented.
3. Additional context: **Wu, Lin (2010), Relevance-Zone-Oriented
   Proof Search for Connect6**, IEEE TCIAIG 2(3), 191–207,
   [DOI and abstract at the authors' university](https://scholar.nycu.edu.tw/en/publications/relevance-zone-oriented-proof-search-for-connect6/).
   The abstract describes a specialised proof search using relevance zones.
   This is a related approach; v3 uses the existing alpha-beta search.

## Nine features and the formula

The following are computed separately for each colour:

| Feature | Meaning | Initial weight |
|---|---|---:|
| `line_1` … `line_5` | Number of windows of length 6 with no opponent stones and 1 … 5 friendly stones | 1, 4, 16, 64, 256 |
| `threat_1` | 1 if all immediate wins can be blocked with one stone | 600 |
| `threat_2` | 1 if one stone is insufficient, but two are enough | 3000 |
| `threat_3` | 1 if two defensive stones are insufficient | 15000 |
| `connectivity` | Sum of pairwise connectivity contributions between friendly stones on potential lines | 2 |

Position evaluation:

`E = sum(weight[name] * (black_features[name] - white_features[name]))`.

A positive value means an advantage for black. A terminal win for black/white
scores +1000000/−1000000 regardless of the weights. A full board without six
in a row scores 0. For the initial weights, even the upper bound on the ordinary
sum is smaller than the win score. Weights are set manually in `Defines.EVAL_WEIGHTS`;
`SearchEngine(weights)` accepts another complete set for future training in v5.

### How threats are handled

For each unblocked window containing four or five stones, the empty cells
that can complete six on the next move are stored. A defence must occupy
at least one cell in EVERY such set.

If all sets share a cell, one defensive stone is enough. Otherwise, all ways
of covering the sets with two stones are checked. If none exists, `threat_3`
is set: this means **at least three**, rather than an exact count for larger
values. Intersections between different directions are accounted for.
Thus, the Wu–Huang threat definition is applied to the entire position,
rather than simply summing individual windows or directions.

`threat_3` is a strong evaluation feature, not a terminal win condition:
the opponent may have an immediate win of their own. Checking for an own win
therefore always precedes defence. Unblocked windows in `line_k` may overlap:
these are deliberate features of potential, not a count of independent threats.
These two meanings must not be confused.

### How connectivity is handled

Horizontal, vertical, and diagonal lines are considered. An opponent's stone
splits a line into separate segments; a segment shorter than six cells cannot
produce a win. In the remaining segments, each pair of friendly stones at
distance `d <= 5` is counted once, contributing `6 - d`. Nearby stones
contribute more, and influence does not pass through an opponent's stone.

**The candidate radius remains 3.** Distance 5 concerns the evaluation of
stones already on the board, not an expansion of the move-generation area.

## Pair generation

1. As in v2, first check for an own immediate win, then for defences against
   all of the opponent's immediate wins. Critical cells are not lost because
   of the normal candidate limit.
2. In a normal position, the local radius-3 area is ranked. The top 12
   first-stone candidates are selected; the second-stone pool contains up to 24 cells.
3. The first stone is temporarily placed on the board. Second cells are
   re-evaluated in the changed position. Up to `12 - i` second cells are
   considered for the first candidate at index `i`. All second cells remain
   in the original local area; the temporary stone does not expand it.
4. Unique pairs are sorted by terminal outcome, then threat strength
   (0/1/2/at least 3), the number of unblocked fours/fives, and the weighted
   evaluation. Up to 24 pairs are passed to the search, as in v2.

All temporary placements, including those used to select the second stone,
are undone via `finally`. The more complex evaluation can take longer than
in v2; any improvement in decision quality must be compared on a shared set
of positions in the experimental part. The maximum depth still remains
2 full moves.

## Running and checks

Run `python3 main.py` or select the executable `v3_threat_evaluation/main.py`
in the same GUI. The name is `tbe`; commands, `depth` units (seconds), stdout
responses, and stderr diagnostic metrics are the same as in v2.
