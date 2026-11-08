"""The teacher's stdin/stdout protocol, with time budgets in seconds."""

import json
import math
import sys

from defines import Defines
from search_engine import SearchEngine
from tools import board_winner, empty_points, init_board, make_move, move2msg, msg2move, print_board


class GameEngine:
    def __init__(self, name=Defines.ENGINE_NAME):
        self.m_engine_name = name
        self.m_time_limit = Defines.TIME_LIMIT
        self.m_board = [[0] * Defines.GRID_NUM for _ in range(Defines.GRID_NUM)]
        self.m_search_engine = SearchEngine()
        self.init_game()

    def init_game(self):
        init_board(self.m_board)
        self.m_next_color = Defines.BLACK

    def on_help(self):
        print("name | print | exit/quit | black XXXX | white XXXX | next | move XXXX\n"
              "new black/white/xxx | depth SECONDS | vcf | unvcf | help", flush=True)

    def place(self, text, color):
        make_move(self.m_board, msg2move(text), color)
        self.m_next_color = color ^ 3

    def search_a_move(self):
        if board_winner(self.m_board) or not empty_points(self.m_board):
            raise ValueError("The game is already over")
        move = self.m_search_engine.choose_move(self.m_board, self.m_next_color, self.m_time_limit)
        make_move(self.m_board, move, self.m_next_color)
        self.m_next_color ^= 3
        # The GUI reads stdout only; experiments can capture stderr separately.
        print("metrics " + json.dumps(self.m_search_engine.stats), file=sys.stderr, flush=True)
        print("move " + move2msg(move), flush=True)

    def handle(self, line):
        parts = line.strip().split()
        if not parts:
            return True
        command, args = parts[0].lower(), parts[1:]
        if command in ("quit", "exit") and not args:
            return False
        if command == "name" and not args:
            print("name " + self.m_engine_name, flush=True)
        elif command == "print" and not args:
            print_board(self.m_board)
            sys.stdout.flush()
        elif command == "help" and not args:
            self.on_help()
        elif command in ("vcf", "unvcf") and not args:
            pass  # Accepted and ignored, as required by the statement.
        elif command == "new" and len(args) == 1 and args[0] in ("black", "white", "xxx"):
            self.init_game()
            if args[0] == "black":
                self.search_a_move()  # Preserve the template's automatic opening.
        elif command == "depth" and len(args) == 1:
            seconds = float(args[0])
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("depth requires a positive finite time limit in seconds")
            self.m_time_limit = seconds
        elif command in ("black", "white") and len(args) == 1:
            self.place(args[0], Defines.BLACK if command == "black" else Defines.WHITE)
        elif command == "move" and len(args) == 1:
            self.place(args[0], self.m_next_color)
            self.search_a_move()
        elif command == "next" and not args:
            self.search_a_move()
        else:
            raise ValueError("Unknown command or invalid arguments: " + line.strip())
        return True

    def run(self):
        for line in sys.stdin:
            try:
                if not self.handle(line):
                    break
            except ValueError as error:
                # Reject malformed commands explicitly, without changing cells
                # or hiding unexpected programming errors.
                print("error " + str(error), file=sys.stderr, flush=True)
