#!/usr/bin/env python3
"""Turn the recorded demo of shape into the README's GIF and its two stills.

    uv run --no-project --with pyte --with pillow python3 docs/demo/render.py

It works from any folder. It reads docs/demo/demo.cast, which record.py writes,
and writes these files in docs/img:

    demo.gif      the whole recording, as agg draws it
    NAME.png      one still for each marker in the cast: list.png and outline.png

Before it saves a still, it replays the recording through a terminal emulator
(pyte) to the moment of the still and checks that the text in EXPECT is on that
screen, so a storyboard that has drifted stops the run instead of saving the
wrong picture.

It needs agg (https://github.com/asciinema/agg), which it looks for in --agg,
then in the AGG environment variable, then on the PATH. It also needs the font
DejaVu Sans Mono, and a Python with pyte and Pillow; the uv command above gives
it one without installing anything. Its files made on the way go in a temporary
folder (set TMPDIR to choose where), which it deletes at the end.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pyte
from pyte.screens import Margins
from PIL import Image

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))           # the repository
CAST = os.path.join(HERE, "demo.cast")
IMG = os.path.join(ROOT, "docs", "img")
GIF = os.path.join(IMG, "demo.gif")

# ---- how it looks: edit here ----

FONT = "DejaVu Sans Mono"       # the terminal's font, as agg finds it
FONT_SIZE = 16                  # pixels
LINE_HEIGHT = 1.2
THEME = "dracula"
FPS = 15                        # the most frames a second the GIF holds

# What each still must show: text that is on the screen at its marker.
EXPECT = {
    "list": "> orders.fulfil",
    "outline": "▶ new · start",
}


# ---- the terminal emulator: pyte, with two scroll sequences ncurses uses ----

class Screen(pyte.Screen):
    """pyte's screen, with CSI n S and CSI n T (scroll the region up or down n lines)."""

    def scroll_up(self, count=None, *args, **kwargs):
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for _ in range(max(1, count or 1)):
            for y in range(top, bottom):
                self.buffer[y] = self.buffer[y + 1]
            self.buffer.pop(bottom, None)
        self.dirty.update(range(self.lines))

    def scroll_down(self, count=None, *args, **kwargs):
        top, bottom = self.margins or Margins(0, self.lines - 1)
        for _ in range(max(1, count or 1)):
            for y in range(bottom, top, -1):
                self.buffer[y] = self.buffer[y - 1]
            self.buffer.pop(top, None)
        self.dirty.update(range(self.lines))


class Stream(pyte.Stream):
    csi = dict(pyte.Stream.csi, S="scroll_up", T="scroll_down")


def read_cast(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


def screens_at(events, header, times):
    """The screen's text rows at each time, replaying the output through the emulator."""
    screen = Screen(header["width"], header["height"])
    stream = Stream(screen)
    found, i = {}, 0
    for t in sorted(times):
        while i < len(events) and events[i][0] <= t:
            if events[i][1] == "o":
                stream.feed(events[i][2])
            i += 1
        found[t] = list(screen.display)
    return [found[t] for t in times]


# ---- running agg ----

def run(command):
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit("render.py: this command failed with exit %d:\n%s\n%s"
                         % (done.returncode, " ".join(command), done.stderr[-3000:]))
    return done.stdout


def last_hold(events):
    """How long the last screen stays: from the last output to the end of the recording.
    agg skips the empty event that marks the end, so the hold is given to it this way."""
    drawn = [e[0] for e in events if e[1] == "o" and e[2]]
    return max(0.5, events[-1][0] - drawn[-1]) if drawn else 1.0


def agg(program, events, cast, gif, extra=()):
    run([program, "-q", "--font-family", FONT, "--font-size", str(FONT_SIZE), "--line-height", str(LINE_HEIGHT),
         "--theme", THEME, "--idle-time-limit", "3600", "--last-frame-duration", "%.3f" % last_hold(events),
         "--fps-cap", str(FPS), *extra, cast, gif])


def frames(gif):
    """Every frame of a GIF as an RGB image, and the GIF's length in seconds."""
    image = Image.open(gif)
    out, length = [], 0
    for n in range(getattr(image, "n_frames", 1)):
        image.seek(n)
        length += image.info.get("duration", 0)
        out.append(image.convert("RGB"))
    return out, length / 1000.0


def stills(program, events, header, work):
    """Save one PNG for each marker in the cast, after checking what its screen shows."""
    markers = [(e[0], e[2]) for e in events if e[1] == "m"]
    if not markers:
        raise SystemExit("render.py: the cast has no markers, so there is no still to take.")
    times = [t for t, _name in markers]
    gif = os.path.join(work, "stills.gif")
    agg(program, events, CAST, gif, extra=["--select", ",".join("%.3f" % t for t in times)])
    images, _length = frames(gif)
    if len(images) != len(markers):
        raise SystemExit("render.py: agg gave %d frames for %d stills." % (len(images), len(markers)))
    saved = []
    for (t, name), image, screen in zip(markers, images, screens_at(events, header, times)):
        want = EXPECT.get(name)
        if want and not any(want in row for row in screen):
            raise SystemExit("render.py: the still %s at %.1f seconds should show %r, and it does not. "
                             "The screen at that moment is:\n%s" % (name, t, want, "\n".join(screen)))
        path = os.path.join(IMG, name + ".png")
        image.save(path, optimize=True)
        saved.append(path)
    return saved


def main(argv=None):
    ap = argparse.ArgumentParser(description="Turn the recorded demo of shape into the README's GIF and stills.")
    ap.add_argument("--agg", default=os.environ.get("AGG") or "agg",
                    help="This is the agg program to run. The default is $AGG, or else agg on the PATH.")
    args = ap.parse_args(argv)
    program = args.agg if os.sep in args.agg else shutil.which(args.agg)
    if not program:
        raise SystemExit("render.py: agg was not found. Put it on the PATH, set AGG, or pass --agg PATH.")
    if not os.path.isfile(CAST):
        raise SystemExit("render.py: %s is missing. Run docs/demo/record.py first." % os.path.relpath(CAST, ROOT))
    header, events = read_cast(CAST)
    os.makedirs(IMG, exist_ok=True)
    work = tempfile.mkdtemp(prefix="shape-demo-")
    try:
        agg(program, events, CAST, GIF)
        saved = stills(program, events, header, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    images, length = frames(GIF)
    width, height = images[0].size
    print("The GIF is %s: %d by %d pixels, %.1f seconds, %d frames, %.2f MB."
          % (os.path.relpath(GIF, ROOT), width, height, length, len(images), os.path.getsize(GIF) / 1e6))
    for path in saved:
        print("The still %s is %d KB." % (os.path.relpath(path, ROOT), os.path.getsize(path) // 1000))
    return 0


if __name__ == "__main__":
    sys.exit(main())
