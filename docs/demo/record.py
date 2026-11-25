#!/usr/bin/env python3
"""Record a short demo of shape as an asciicast file, for the README.

    python3 docs/demo/record.py

It works from any folder. It starts a plain bash on a pseudo-terminal of COLS
columns by ROWS rows, in the repository's examples folder, so the list shows the
three example programs. It types the word shape at the prompt, which runs
python3 bin/shape from this repository. Then it presses the keys in STORYBOARD
with the pauses written there, and writes one file beside this script:

    demo.cast   everything the terminal received, as asciicast v2: one JSON
                header line, then one [seconds, "o", text] line per piece of
                output, and one [seconds, "m", name] marker for each still

render.py turns that file into the GIF and the stills in docs/img.

To change the demo, edit STORYBOARD below and run this script again. It runs the
real bin/shape and changes nothing in the repository except demo.cast. It needs
only the standard library of Python 3.9 or later and bash, on Linux or macOS.
Node.js must be on the PATH, because one of the examples is a JavaScript program.
"""
import codecs
import fcntl
import json
import os
import pty
import shlex
import struct
import subprocess
import sys
import termios
import threading
import time

# ---- what the viewer sees: edit here ----

COLS, ROWS = 100, 28        # the terminal's size in characters
PROMPT = "examples $ "      # the shell prompt the recording starts on
TYPE_DELAY = 0.12           # seconds between the letters of a typed word
LEAD = 0.5                  # seconds before a beat's first key
GAP = 0.6                   # seconds between keys, unless a beat gives its own
SETTLE = 0.15               # seconds after a beat's last key before its hold starts

# A beat is a few keys and then a pause. Its keys are pressed in order, GAP (or
# the beat's gap) apart, then the screen is held for hold seconds. When a beat
# names a still, a marker with that name is put in the cast just before the end
# of the hold, and render.py saves that moment as docs/img/NAME.png. wait_for
# holds the beat until that text has been drawn, for a screen that takes a
# moment to open.
#
# Keys: "type:WORD" types WORD a letter at a time; "enter", "esc", "up", "down",
# "space"; any single character, such as "a", "?", "G" or "q"; "down*12" presses
# a key 12 times, gap apart; "wait:0.5" waits half a second instead of the gap.
STORYBOARD = [
    # Type shape; the list of the three example programs opens.
    dict(keys=["type:shape", "wait:0.4", "enter"], wait_for="PROGRAM", hold=1.4),
    # Move down to orders.fulfil; the sentence under the list changes.
    dict(keys=["down"], hold=2.0, still="list"),
    # Open it, and stay on the top of the outline.
    dict(keys=["enter"], wait_for="new", hold=2.8, still="outline"),
    # Scroll down slowly: "Ways it goes wrong", then "Routes", then "Conditions".
    dict(keys=["down*12"], gap=0.15, hold=1.5),
    dict(keys=["down*8"], gap=0.15, hold=1.5),
    dict(keys=["down*5"], gap=0.15, hold=2.2),
    # Esc goes back to the list; move down to download.fetch and open it.
    dict(keys=["esc", "down", "enter"], gap=0.7, hold=2.6),
    # The question mark shows how to read an outline; any key goes back.
    dict(keys=["?"], hold=3.4),
    dict(keys=["space"], hold=1.0),
    # q closes shape, and the prompt comes back.
    dict(keys=["q"], hold=1.2),
]

# ---- how it is recorded: no need to edit below ----

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))           # the repository
EXAMPLES = os.path.join(ROOT, "examples")
CAST = os.path.join(HERE, "demo.cast")

# What each key sends. The arrows are in the form a curses program asks for
# (xterm application mode), and Enter is a carriage return, as a keyboard sends.
KEYS = {"enter": b"\r", "esc": b"\x1b", "up": b"\x1bOA", "down": b"\x1bOB",
        "right": b"\x1bOC", "left": b"\x1bOD", "space": b" "}


def shell_env():
    """The environment of the recorded shell: shape is a shell function that runs
    python3 bin/shape from this repository, and the locale draws UTF-8."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("NO_COLOR", "PROMPT_COMMAND", "PS0", "SHAPE_CONFIG", "BASH_ENV", "ENV")}
    env.update(TERM="xterm-256color", PS1=PROMPT, HISTFILE=os.devnull)
    env["BASH_FUNC_shape%%"] = '() {  python3 %s "$@"\n}' % shlex.quote(os.path.join(ROOT, "bin", "shape"))
    locale = env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or ""
    if "UTF-8" not in locale.upper().replace("UTF8", "UTF-8"):
        env["LC_ALL"] = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
    return env


class Recording:
    """A bash on a pseudo-terminal, and every byte it writes with the time it came."""

    def __init__(self, cols, rows):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

        def own_terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.start = time.monotonic()
        self.chunks = []
        self.markers = []
        self.shell = subprocess.Popen(["bash", "--norc", "--noprofile", "-i"], stdin=slave, stdout=slave,
                                      stderr=slave, env=shell_env(), cwd=EXAMPLES, preexec_fn=own_terminal)
        os.close(slave)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        while True:
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                return
            if not chunk:
                return
            self.chunks.append((self.now(), chunk))

    def now(self):
        return time.monotonic() - self.start

    def send(self, data):
        os.write(self.master, data)

    def seen_since(self, index):
        return b"".join(c for _t, c in self.chunks[index:])

    def wait_for(self, text, since, timeout=20.0):
        """Wait until text has been drawn after chunk number since; False if it never was."""
        want, end = text.encode("utf-8"), time.monotonic() + timeout
        while time.monotonic() < end:
            if want in self.seen_since(since):
                return True
            time.sleep(0.05)
        return False

    def close(self):
        try:
            self.send(b"exit\r")
            self.shell.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            self.shell.kill()
            self.shell.wait()
        os.close(self.master)


def press(rec, key, gap):
    """Press one storyboard key; a repeated key is pressed gap seconds apart."""
    if key.startswith("type:"):
        for letter in key[5:]:
            rec.send(letter.encode("utf-8"))
            time.sleep(TYPE_DELAY)
        return
    name, _, times = key.partition("*")
    data = KEYS.get(name, name.encode("utf-8") if len(name) == 1 else None)
    if data is None:
        raise SystemExit("record.py: the storyboard names a key that is not known: %r" % key)
    for i in range(int(times or 1)):
        if i:
            time.sleep(gap)
        rec.send(data)


def play(rec, keys, gap):
    """Press a beat's keys in order: gap seconds between them, or a written wait."""
    for i, key in enumerate(keys):
        if key.startswith("wait:"):
            time.sleep(float(key[5:]))
            continue
        press(rec, key, gap)
        following = keys[i + 1] if i + 1 < len(keys) else None
        if following is None:
            time.sleep(SETTLE)
        elif not following.startswith("wait:"):
            time.sleep(gap)


def record():
    rec = Recording(COLS, ROWS)
    if not rec.wait_for(PROMPT.strip(), 0, timeout=10):
        rec.close()
        raise SystemExit("record.py: the shell prompt did not appear, so nothing was recorded.")
    time.sleep(0.8)
    problems = []
    for n, beat in enumerate(STORYBOARD, start=1):
        mark = len(rec.chunks)
        keys, gap = beat.get("keys", []), beat.get("gap", GAP)
        if keys:
            time.sleep(beat.get("lead", LEAD))
        play(rec, keys, gap)
        if beat.get("wait_for") and not rec.wait_for(beat["wait_for"], mark):
            problems.append("beat %d waited for %r, which never appeared" % (n, beat["wait_for"]))
        hold = beat.get("hold", 3.0)
        if beat.get("still"):
            time.sleep(max(0.0, hold - 0.25))
            rec.markers.append((rec.now(), beat["still"]))
            time.sleep(min(hold, 0.25))
        else:
            time.sleep(hold)
    finished = rec.now()
    tail = rec.seen_since(len(rec.chunks) - 3 if len(rec.chunks) >= 3 else 0)
    chunks = [c for c in rec.chunks if c[0] <= finished]
    markers = rec.markers
    rec.close()
    if PROMPT.strip().encode() not in tail:
        problems.append("the shell prompt did not come back at the end, so shape may not have closed")
    return chunks, markers, finished, problems


def write_cast(chunks, markers, finished):
    decode = codecs.getincrementaldecoder("utf-8")(errors="replace")
    header = {"version": 2, "width": COLS, "height": ROWS, "timestamp": int(time.time()),
              "title": "shape: see the shape of a program",
              "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}
    events = []
    for t, chunk in chunks:
        text = decode.decode(chunk)
        if text:
            events.append([round(t, 6), "o", text])
    events.extend([round(t, 6), "m", name] for t, name in markers)
    events.sort(key=lambda e: e[0])
    events.append([round(finished, 6), "o", decode.decode(b"", final=True)])
    with open(CAST, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def main():
    chunks, markers, finished, problems = record()
    write_cast(chunks, markers, finished)
    print("The recording is %.1f seconds long, at %d columns by %d rows, with %d stills marked."
          % (finished, COLS, ROWS, len(markers)))
    print("It is in %s." % os.path.relpath(CAST, ROOT))
    for problem in problems:
        print("Problem: %s." % problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
