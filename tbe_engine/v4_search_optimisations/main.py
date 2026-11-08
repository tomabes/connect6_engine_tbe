#!/usr/bin/env python3
"""tbe v4. Optional switches support independent optimisation experiments."""

import argparse
from game_engine import GameEngine
from search_engine import SearchEngine


def main():
    parser = argparse.ArgumentParser(description="tbe v4 Connect6 engine")
    parser.add_argument("--no-quiescence", action="store_true")
    parser.add_argument("--no-forward-pruning", action="store_true")
    args = parser.parse_args()
    search = SearchEngine(use_quiescence=not args.no_quiescence,
                          use_forward_pruning=not args.no_forward_pruning)
    GameEngine(search_engine=search).run()


if __name__ == "__main__":
    main()
