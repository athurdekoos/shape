"""A pretend terminal, for the tests of the screen that stays open: start a command on
a pty, read what it draws, press keys."""
import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time

ESCAPES = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[()][A-Za-z0-9]|[=>78])")


class Terminal:
    """with Terminal(exe) as term: term.read_for(2.0); term.press(b"q"); term.wait()"""

    def __init__(self, exe, *args, rows=45, cols=130, cwd=None):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        env = dict(os.environ, TERM="xterm")
        env.pop("NO_COLOR", None)
        env.pop("SHAPE_CONFIG", None)
        self.p = subprocess.Popen([sys.executable, str(exe), *args], stdin=slave, stdout=slave, stderr=slave, env=env,
                                  cwd=cwd)
        os.close(slave)

    def read_for(self, seconds):
        """What was drawn in the next `seconds`, without the escape codes."""
        buf, end = b"", time.time() + seconds
        while time.time() < end:
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
        return ESCAPES.sub("", buf.decode("utf-8", "replace"))

    def press(self, keys):
        os.write(self.master, keys)

    def running(self):
        return self.p.poll() is None

    def wait(self, timeout=5):
        """The command's exit code. What it still writes is read while waiting: on macOS a program
        that closes a terminal waits until its last output has been read."""
        end = time.time() + timeout
        while self.p.poll() is None and time.time() < end:
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    os.read(self.master, 65536)
                except OSError:
                    break
        return self.p.wait(timeout=max(0.1, end - time.time()))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.p.poll() is None:
            self.p.kill()
        os.close(self.master)
