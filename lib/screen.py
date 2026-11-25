"""screen: how shape shows an outline.

An outline is a list of lines, and a line is a list of (text, style) pieces. The
showing is here: to_text() for plain or
coloured text, table() for the printed list, wrap() for a narrow window, Browser and
browse() for the screen that stays open (a list, Enter opens one, Esc goes back),
and sources() and read_source() for the JSON that shape.json names.

shapeview adds what is its own in a subclass of Browser: the columns of its list,
the outline of one thing and the help. Standard library only, Python 3.9 compatible.
"""
from __future__ import annotations

import json
import os
import subprocess


class SourceError(Exception):
    """A source in shape.json could not be read."""


def plural(n: int, one: str, many: str) -> str:
    return "%d %s" % (n, one if n == 1 else many)


# ---- lines as text ----

STYLES = {"title": "1", "head": "1", "state": "1;35", "target": "36", "bad": "1;31", "ok": "32", "dim": "90"}


def to_text(lines: list, color: bool = False) -> str:
    rows = []
    for line in lines:
        row = ""
        for piece, style in line:
            code = STYLES.get(style) if color else None
            row += "\x1b[%sm%s\x1b[0m" % (code, piece) if code and piece else piece
        rows.append(row.rstrip() if not color else row)
    return "\n".join(rows) + "\n"


def table(head: tuple, rows: list) -> list:
    """A printed table: the headings, then one line per row with its first cell as the
    name. The last column is not padded, so it may be a sentence."""
    widths = [max(len(r[i]) for r in [head] + rows) for i in range(len(head))]
    out = [[("  ".join(c.ljust(widths[i]) for i, c in enumerate(head)).rstrip(), "head")]]
    for r in rows:
        out.append([(r[0].ljust(widths[0]) + "  ", "state"),
                    ("  ".join(c.ljust(widths[i + 1]) for i, c in enumerate(r[1:-1])) + "  ", None),
                    (r[-1], None)])
    out.append([])
    return out


def wrap(line: list, width: int) -> list:
    """One line of (text, style) pieces as one or more lines no wider than `width`,
    broken between words. Later lines are indented under the first one's text."""
    text = "".join(t for t, _ in line)
    if width < 20 or len(text) <= width:
        return [line]
    styles = [s for t, s in line for _ in t]
    lead = len(text) - len(text.lstrip(" "))
    first = len(line[0][0])
    if len(line) > 1 and line[0][0].endswith(" ") and first <= width // 2:
        hang = first                          # a label, then words: continue under the words
    else:
        hang = min(lead + 4, width // 2) if lead else 0   # a sentence from the margin stays at the margin

    def pieces(start, end, indent):
        out = [(" " * indent, None)] if indent else []
        i = start
        while i < end:
            j = i
            while j < end and styles[j] == styles[i]:
                j += 1
            out.append((text[i:j], styles[i]))
            i = j
        return out

    rows, start, indent = [], 0, 0
    while len(text) - start > width - indent:
        limit = start + width - indent
        cut = text.rfind(" ", start + (lead if start == 0 else 0) + 1, limit + 1)
        if cut <= start:
            cut = limit                       # one word longer than the line: cut it
        rows.append(pieces(start, cut, indent))
        start = cut
        while start < len(text) and text[start] == " ":
            start += 1
        indent = hang
    if start < len(text):
        rows.append(pieces(start, len(text), indent))
    return rows


# ---- where the JSON comes from ----

def sources(config: str) -> list:
    """The list of sources in the file `config`, such as a shape.json.
    A source is {"file": PATH} or {"command": [ARGV...]}."""
    try:
        with open(config, encoding="utf-8") as fh:
            found = json.load(fh)
    except OSError as exc:
        raise SourceError("%s: %s" % (config, exc.strerror or exc))
    except ValueError as exc:
        raise SourceError("%s: not JSON (%s)" % (config, exc))
    if not isinstance(found, list):
        raise SourceError('%s: it should hold a list of sources, such as [{"file": "program.json"}]' % config)
    return found


def read_source(root: str, src: dict):
    if isinstance(src.get("file"), str):
        label = src["file"]
        try:
            with open(os.path.join(root, src["file"]), encoding="utf-8") as fh:
                raw = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise SourceError("%s: %s" % (label, getattr(exc, "strerror", None) or exc))
    elif isinstance(src.get("command"), list) and src["command"] and all(isinstance(c, str) for c in src["command"]):
        command = list(src["command"])
        label = " ".join(command)
        first = os.path.join(root, command[0])
        if os.path.isfile(first):
            command[0] = first
        try:
            done = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise SourceError("%s: it did not finish in 60 seconds" % label)
        except OSError as exc:
            raise SourceError("%s: %s" % (label, exc.strerror or exc))
        if done.returncode != 0:
            raise SourceError("%s: exit %d: %s" % (label, done.returncode, done.stderr.strip() or "(it said nothing)"))
        raw = done.stdout
    else:
        raise SourceError('a source needs "file" (a path) or "command" (a list of words), and this has neither: %s'
                          % json.dumps(src))
    try:
        return label, json.loads(raw)
    except ValueError as exc:
        raise SourceError("%s: not JSON (%s)" % (label, exc))


# ---- the screen that stays open ----

class Browser:
    """What the open screen shows and how keys change it. No terminal in here, so it
    can be tested: key() takes the name of a key, frame() gives the lines to draw.

    A command subclasses it and says what is its own: the words at the top, the
    columns of the list, what to say about the picked row, the outline of one model,
    what the `a` key is called, and the help."""

    name = ""           # the command, shown at the top of the list
    tagline = ""        # what the command is for, beside the name
    head = ()           # the headings of the list's columns
    help_lines = []     # the "how to read" screen

    def __init__(self, models: list, start=None, more: bool = False):
        self.models = models
        self.cursor = start or 0
        self.screen = "outline" if start is not None else "list"
        self.before_help = self.screen
        self.scroll = 0
        self.more = more
        self.done = False
        self.above = []     # lines shown above the list, such as where the programs came from
        self.below = []     # lines shown under it, such as what could not be read

    def row(self, model: dict) -> tuple:
        """The cells of one model's row in the list, one per heading."""
        raise NotImplementedError

    def picked(self, model: dict) -> list:
        """The lines under the list that say what the picked model is."""
        return []

    def outline(self, model: dict, more: bool) -> list:
        """The outline of one model as lines; `more` is what the `a` key switches on."""
        raise NotImplementedError

    def more_key(self, more: bool) -> str:
        """What the `a` key does next, for the key line (such as "a all routes")."""
        return "a more"

    def key(self, name: str, page: int = 10) -> None:
        if name == "quit":
            self.done = True
        elif self.screen == "help":
            self.screen, self.scroll = self.before_help, 0
        elif name == "help":
            self.before_help, self.screen, self.scroll = self.screen, "help", 0
        elif self.screen == "list":
            if name == "down":
                self.cursor = min(self.cursor + 1, len(self.models) - 1)
            elif name == "up":
                self.cursor = max(self.cursor - 1, 0)
            elif name == "top":
                self.cursor = 0
            elif name == "bottom":
                self.cursor = len(self.models) - 1
            elif name == "open" and self.models:
                self.screen, self.scroll = "outline", 0
        else:
            step = {"down": 1, "up": -1, "page_down": page, "page_up": -page}.get(name)
            if step:
                self.scroll = max(0, self.scroll + step)     # frame() stops it at the bottom
            elif name == "top":
                self.scroll = 0
            elif name == "bottom":
                self.scroll = 10 ** 9
            elif name == "all":
                self.more = not self.more
            elif name == "back":
                self.screen, self.scroll = "list", 0

    def _list(self) -> list:
        out = [[(self.name, "title"), ("   " + self.tagline, "dim")], []]
        if self.above:
            out.extend(self.above)
            out.append([])
        if self.models:
            rows = [self.row(m) for m in self.models]
            widths = [max(len(r[i]) for r in [self.head] + rows) for i in range(len(self.head))]

            def cells(r):
                return "  ".join(c.ljust(widths[i]) for i, c in enumerate(r))

            out.append([("  " + cells(self.head), "head")])
            for i, r in enumerate(rows):
                picked = i == self.cursor
                out.append([(("> " if picked else "  ") + cells(r), "sel" if picked else None)])
            out.append([])
            out.extend(self.picked(self.models[self.cursor]))
        else:
            out.append([("Nothing is listed yet.", None)])
        if self.below:
            out.append([])
            out.extend(self.below)
        return out

    def frame(self, height: int, width: int):
        """(the lines to draw, the key line) for a window of this size."""
        room = max(1, width - 1)
        if self.screen == "list":
            lines = self._list()
            keys = "↑↓ move   enter open   ? how to read   q quit"
        elif self.screen == "help":
            lines = self.help_lines
            keys = "any key goes back   q quit"
        else:
            lines = self.outline(self.models[self.cursor], self.more)
            keys = "↑↓ scroll   space page   %s   esc back   ? how to read   q quit" % self.more_key(self.more)
        lines = [row for line in lines for row in wrap(line, room)]
        body = max(1, height - 1)
        if self.screen == "list":                     # keep the picked row in view
            at = next((n for n, line in enumerate(lines) if line and line[0][1] == "sel"), 0)
            self.scroll = max(0, at - body + 4) if at >= body - 3 else 0
        self.scroll = max(0, min(self.scroll, len(lines) - body))
        shown = lines[self.scroll:self.scroll + body]
        if self.screen == "outline" and len(lines) > body:
            keys += "   %d%%" % (100 * (self.scroll + body) // len(lines))
        return shown, keys


def browse(browser: Browser) -> int:
    """Open the screen on `browser` and stay until q."""
    import curses
    import locale

    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")

    def run(scr):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        attr = {"title": curses.A_BOLD, "head": curses.A_BOLD, "sel": curses.A_REVERSE, "dim": curses.A_DIM,
                "state": curses.A_BOLD, "target": curses.A_NORMAL, "bad": curses.A_BOLD, "ok": curses.A_NORMAL}
        if curses.has_colors() and not os.environ.get("NO_COLOR"):
            curses.use_default_colors()
            for n, (style, colour, extra) in enumerate((("state", curses.COLOR_MAGENTA, curses.A_BOLD),
                                                        ("target", curses.COLOR_CYAN, 0),
                                                        ("bad", curses.COLOR_RED, curses.A_BOLD),
                                                        ("ok", curses.COLOR_GREEN, 0)), start=1):
                curses.init_pair(n, colour, -1)
                attr[style] = curses.color_pair(n) | extra
        names = {curses.KEY_DOWN: "down", ord("j"): "down", curses.KEY_UP: "up", ord("k"): "up",
                 curses.KEY_ENTER: "open", 10: "open", 13: "open", curses.KEY_RIGHT: "open", ord("l"): "open",
                 27: "back", curses.KEY_LEFT: "back", curses.KEY_BACKSPACE: "back", 127: "back", ord("h"): "back",
                 ord(" "): "page_down", curses.KEY_NPAGE: "page_down", curses.KEY_PPAGE: "page_up",
                 ord("b"): "page_up", curses.KEY_HOME: "top", ord("g"): "top", curses.KEY_END: "bottom",
                 ord("G"): "bottom", ord("a"): "all", ord("?"): "help", ord("q"): "quit", ord("Q"): "quit"}
        was = None
        while not browser.done:
            height, width = scr.getmaxyx()
            body, keys = browser.frame(height, width)
            if browser.screen != was:       # a different screen: repaint all of it
                scr.clear()
                was = browser.screen
            else:
                scr.erase()
            for y, line in enumerate(body):
                x = 0
                for text, style in line:
                    if style == "sel":
                        text = text.ljust(max(0, width - 1))
                    try:
                        scr.addnstr(y, x, text, max(0, width - 1 - x), attr.get(style, curses.A_NORMAL))
                    except curses.error:
                        pass
                    x += len(text)
            try:
                scr.addnstr(height - 1, 0, keys, max(0, width - 1), curses.A_DIM)
            except curses.error:
                pass
            scr.refresh()
            code = scr.getch()
            if browser.screen == "help" and code not in (curses.KEY_RESIZE, -1):
                browser.key("quit" if code in (ord("q"), ord("Q")) else "any")
            elif code in names:
                browser.key(names[code], page=max(1, height - 3))

    curses.wrapper(run)
    return 0
