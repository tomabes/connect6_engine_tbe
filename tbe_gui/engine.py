from time import *;
import os;
import random;
from subprocess import *;
from threading import *;
from pathlib import Path
import sys
from engine_process import EngineError, EngineProcess

class Move:
    NONE = 0;
    BLACK = 1;
    WHITE = 2;
    EDGE = 19;
    
    def __init__(self, color = NONE, x1 = -1, y1 = -1, x2 = -1, y2 = -1):
        self.color = color;
        self.x1 = x1;
        self.y1 = y1;
        self.x2 = x2;
        self.y2 = y2;

    def __str__(self):
        return 'color: {0}, x1: {1}, y1: {2}, x2: {3}, y2: {4}'.format(self.color, self.x1, self.y1, self.x2, self.y2);

    def fromCmd(cmd, color = None):
        # print(cmd);
        # print(self);
        cmd = cmd.strip();
        if cmd.startswith('move '):
            cmd = cmd[5:].upper();
            if len(cmd) not in (2, 4) or any(c not in 'ABCDEFGHIJKLMNOPQRS' for c in cmd):
                raise ValueError('Invalid engine move: ' + cmd)
            if len(cmd) == 2:
                cmd = cmd*2;
            m = Move(color);
            m.x1 = ord(cmd[0]) - ord('A');
            m.y1 = ord(cmd[1]) - ord('A');
            m.x2 = ord(cmd[2]) - ord('A');
            m.y2 = ord(cmd[3]) - ord('A');
            return m;
        
        return None;

    def toCmd(self):  
        cmd = 'move ' + self.cmd() + '\n';
        print('Cmd:', cmd);
        return cmd;

    def toPlaceCmd(self):
        if self.color == Move.BLACK:
            cmd = 'black ';
        elif self.color == Move.WHITE:
            cmd = 'white ';
        else:
            return 'None Place Cmd\n';
        cmd += self.cmd() + '\n';
        # print('Cmd:', cmd);
        return cmd;

    def cmd(self):
        base = ord('A');
        return chr(base + self.x1) + chr(base + self.y1) + chr(base + self.x2) + chr(base + self.y2);

    def invalidate(self):
        self.color= None;
        self.x1 = -1;
        self.y1 = -1;
        self.x2 = -1;
        self.y2 = -1;

    def isValidated(self):
        if self.color != Move.BLACK and self.color != Move.WHITE:
            return False;
        if Move.isValidPosition(self.x1, self.y1) and Move.isValidPosition(self.x2, self.y2):
            return True;

        return False;

    def isValidPosition(x, y):
        if x >= 0 and x < Move.EDGE and y >= 0 and y < Move.EDGE:
            return True;
        return False;

class GameEngine:
    def __init__(self):
        self.fileName = None
        self.connection = None
        self.proc = None
        self.move = Move()
        self.color = Move.NONE
        self.msg = ""
        self.setName('Unknown')

    def init(self, fileName=None, depth=None, vcf=None):
        self.release()
        if fileName is not None and fileName.strip():
            self.fileName = str(Path(fileName).resolve())
        if self.fileName is None:
            raise EngineError("No engine executable was selected")
        self.setName(self.fileName)
        try:
            self.connection = EngineProcess(
                [self.fileName], cwd=str(Path(self.fileName).parent),
                stderr_sink=lambda line: print(line, end="", file=sys.stderr, flush=True))
            self.proc = self.connection.proc
            self.sendCmd('name')
            reply = self.connection.expect('name ', timeout=5.0)
            self.setName(reply.split(' ', 1)[1].strip())
            if depth is not None:
                self.sendCmd('depth ' + str(depth))
            if vcf is not None:
                self.sendCmd('vcf' if vcf else 'unvcf')
        except (OSError, EngineError, TimeoutError):
            self.release()
            raise
        self.move.invalidate()
        return True

    def isReady(self):
        return self.proc is not None and self.proc.poll() is None

    def setName(self, name):
        self.name = self.shortName = name
        if len(self.shortName) > 10 and '.' in self.shortName:
            self.shortName = next(part for part in self.shortName.split('.') if part)
        if len(self.shortName) > 10:
            self.shortName = self.shortName[:8] + '...'

    def release(self):
        connection = self.connection
        self.connection = None
        self.proc = None
        if connection is not None:
            connection.close()
        self.move.invalidate()
        self.msg = ""

    def next(self, moveList=None):
        commands = ['new xxx']
        commands.extend(move.toPlaceCmd().strip() for move in (moveList or []))
        commands.append('next')
        self.sendCmd('\n'.join(commands))

    def sendCmd(self, cmd):
        if self.connection is None:
            raise EngineError("Engine is not connected")
        self.connection.send(cmd)

    def waitForNextMsg(self, timeout=30.0):
        connection = self.connection
        if connection is None:
            raise EngineError("Engine is not connected")
        self.msg = connection.readline(timeout)
        return self.msg
