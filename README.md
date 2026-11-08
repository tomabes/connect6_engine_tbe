# Connect6 Game Engine — tbe

A Python engine for Connect6. Five versions explore minimax, alpha-beta pruning, threat-based evaluation, search optimisations, and evaluation-weight learning.

**The final engine is in `tbe_engine/v5_final/`.**

Run the final engine from the repository root with `python3 tbe_engine/v5_final/main.py`.

## Project structure

- `tbe_engine/`
  - `v1_baseline/` — basic minimax engine.
  - `v2_alpha_beta/` — alpha-beta pruning and move ordering.
  - `v3_threat_evaluation/` — threat-based evaluation.
  - `v4_search_optimisations/` — quiescence search and forward pruning.
  - `v5_final/` — final engine and weight-learning experiments.
  - `benchmark/` — test positions, tournaments, and results.
  - `game_screenshots_and_logs/` — gameplay screenshots and logs.
- `tbe_gui/` — graphical interface.
- `cloudict_native/` — Cloudict reference opponent and build script.
- `report_en.pdf/` — English PDF report.
