"""Bounded stdin/stdout connection shared by the GUI and offline training."""

import os
from pathlib import Path
from queue import Empty, Full, Queue
import signal
import subprocess
from threading import Thread
import time


class EngineError(RuntimeError):
    """The engine exited or violated the text protocol."""


class EngineProcess:
    def __init__(self, command, cwd=None, stderr_sink=None):
        options = {}
        if os.name == "nt":
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            options["startupinfo"] = info
        else:
            options["start_new_session"] = True
        self.proc = subprocess.Popen(
            [str(arg) for arg in command], cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", bufsize=1, **options)
        self.lines = Queue(maxsize=256)
        self.stderr = []
        self.failure = None
        self.closed = False
        self.stderr_sink = stderr_sink
        self.readers = [Thread(target=self._read_stdout, daemon=True),
                        Thread(target=self._read_stderr, daemon=True)]
        for reader in self.readers:
            reader.start()

    def _fail(self, message):
        self.failure = message
        if self.proc.poll() is None:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass
        try:
            self.lines.put_nowait(None)
        except Full:
            pass  # readline checks failure before consuming the queue.

    def _read_stdout(self):
        try:
            while True:
                line = self.proc.stdout.readline(4097)
                if len(line) > 4096:
                    self._fail("Engine stdout line exceeds 4096 characters")
                    return
                try:
                    self.lines.put_nowait(line if line else None)
                except Full:
                    self._fail("Engine stdout queue overflow")
                    return
                if not line:
                    return
        except (OSError, ValueError) as error:
            if not self.closed:
                self._fail("Cannot read engine stdout: " + str(error))

    def _read_stderr(self):
        size = 0
        try:
            while True:
                line = self.proc.stderr.readline(4097)
                if not line:
                    return
                size += len(line)
                if len(line) > 4096 or size > 131072:
                    self._fail("Engine stderr exceeds diagnostic limits")
                    return
                self.stderr.append(line)
                if self.stderr_sink is not None:
                    self.stderr_sink(line)
        except (OSError, ValueError) as error:
            if not self.closed:
                self._fail("Cannot read engine stderr: " + str(error))

    def send(self, text):
        if self.closed or self.proc.poll() is not None:
            raise EngineError(f"Engine is not running (exit {self.proc.poll()})")
        if not text.endswith("\n"):
            text += "\n"
        try:
            self.proc.stdin.write(text)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise EngineError("Cannot send engine command: " + str(error)) from error

    def readline(self, timeout):
        if self.closed:
            raise EngineError("Engine connection was closed")
        if self.failure is not None:
            raise EngineError(self.failure)
        if timeout <= 0:
            raise TimeoutError("Engine response deadline expired")
        deadline = time.monotonic() + timeout
        try:
            line = self.lines.get(timeout=timeout)
        except Empty as error:
            raise TimeoutError("Engine did not respond before the deadline") from error
        if time.monotonic() >= deadline:
            raise TimeoutError("Engine response arrived after the deadline")
        if self.failure is not None:
            raise EngineError(self.failure)
        if line is None:
            code = self.proc.poll()
            if code is None:
                try:
                    code = self.proc.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    code = "still running, stdout closed"
            raise EngineError(f"Engine closed stdout (exit {code}). "
                              + "".join(self.stderr[-3:]).strip())
        return line

    def expect(self, prefix, timeout):
        deadline = time.monotonic() + timeout
        while True:
            line = self.readline(deadline - time.monotonic())
            if line.startswith(prefix):
                return line.strip()

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Wake a GUI thread currently waiting for a reply.
        try:
            self.lines.put_nowait(None)
        except Full:
            pass
        if self.proc.poll() is None:
            try:
                if os.name == "nt":
                    self.proc.terminate()
                else:
                    os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # Process exited between poll and the signal.
            try:
                self.proc.wait(timeout=0.35)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "nt":
                        self.proc.kill()
                    else:
                        os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.proc.wait(timeout=0.35)
        else:
            self.proc.wait()
        for reader in self.readers:
            reader.join(timeout=0.1)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            stream.close()


def native_cloudict_path():
    return Path(__file__).resolve().parent / "engines" / "cloudict_native"
