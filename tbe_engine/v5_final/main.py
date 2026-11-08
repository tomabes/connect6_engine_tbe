#!/usr/bin/env python3
"""tbe v5 final: v4 search with weights chosen by train.py."""

import argparse
from game_engine import GameEngine
from search_engine import SearchEngine, load_weights


def main():
    parser = argparse.ArgumentParser(description="tbe v5 final Connect6 engine")
    parser.add_argument("--no-quiescence", action="store_true")
    parser.add_argument("--no-forward-pruning", action="store_true")
    parser.add_argument("--weights", help="Alternative weights JSON for controlled experiments")
    args = parser.parse_args()
    search = SearchEngine(weights=load_weights(args.weights), use_quiescence=not args.no_quiescence,
                          use_forward_pruning=not args.no_forward_pruning)
    GameEngine(search_engine=search).run()


if __name__ == "__main__":
    main()
