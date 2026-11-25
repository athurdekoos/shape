"""shapeview: a program's state machine as an outline a person can read.

The input is JSON: the description a program prints of the machine it runs
(states, the events each state takes, and for each event its ordered branches).
build() turns one description into a plain model: the states in the order the
program reaches them, every way into a state that needs attention, every route
from the start to an end, the transitions that go back, and the conditions.
render() turns the model into lines of (text, style) pieces, so everything can be
tested without a terminal.

shapeformat.py reads a description strictly and writes out its shorthands. Where the
JSON comes from is a list of sources, usually the shape.json found from the folder
the command was typed in (see find_sources and load_all). check() is what
shape --check prints. The screen that stays open is in screen.py. Standard library
only, Python 3.9 compatible.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shlex
import stat
import sys

import screen
import shapeformat
from screen import SourceError, plural
from shapeformat import FormatError

VERSION = "0.1.0"
CONFIG = "shape.json"  # the list of sources, looked for in the folder shape is typed in and the folders above

PATH_LIMIT = 2000      # stop counting routes past this many; the outline says so
STEP_LIMIT = 200000    # and stop walking after this many steps, whatever was found
PATHS_SHOWN = 8        # routes printed for one end state unless --all is given


# ---- the words written beside a condition ----

SOURCE_LIMIT = 1024 * 1024   # the largest Python file describe() reads, in bytes

_parsed = {}


def _python_text(root: str, path: str):
    """The text of the file at `path`, or None unless its real path is inside the folder
    `root`, it is a regular file and it holds at most SOURCE_LIMIT bytes."""
    top = os.path.realpath(root)
    real = os.path.realpath(os.path.join(top, path))
    if os.path.commonpath([top, real]) != top:
        return None
    # Opened without waiting, so a named pipe cannot hold shape up; then checked by what it is.
    fd = os.open(real, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as fh:
        info = os.fstat(fh.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > SOURCE_LIMIT:
            return None
        data = fh.read(SOURCE_LIMIT + 1)
    if len(data) > SOURCE_LIMIT:
        return None
    return data.decode("utf-8")


def describe(root: str, where: str) -> str:
    """The first paragraph of the docstring of the Python function at `file:line`, or ""
    when the file is not there, is not Python, or the function has none. The file must be
    inside the project folder `root`, a regular file and at most SOURCE_LIMIT bytes.
    It is parsed, never run."""
    path, _, line = (where or "").rpartition(":")
    if not root or not path.endswith(".py") or not (line.isascii() and line.isdigit()):
        return ""
    full = os.path.join(root, path)
    if full not in _parsed:
        try:
            text = _python_text(root, path)
            _parsed[full] = None if text is None else ast.parse(text)
        except (OSError, SyntaxError, ValueError, RecursionError, MemoryError):
            _parsed[full] = None
    tree = _parsed[full]
    if tree is None:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno == int(line):
            doc = ast.get_docstring(node) or ""
            return " ".join(doc.split("\n\n", 1)[0].split())
    return ""


# ---- the model ----

def build(doc: dict, root: str = "") -> dict:
    """The outline model of one machine description. Raises shapeformat.FormatError, which
    is a ValueError, when the description is wrong."""
    doc = shapeformat.read(doc)
    initial, states_doc = doc["initial"], doc["states"]
    attention, goal = doc["attention"], doc["goal"]

    names = []            # every state named anywhere, start first
    outgoing = {}         # state -> [(event, branch), ...] in declared order
    events_of = {}        # state -> [event, ...] in declared order

    def note(name):
        if name not in names:
            names.append(name)

    conditions = {}

    def condition(guard):
        if not guard:
            return None
        name, where = guard["name"], guard["source"]
        if name == "<lambda>":
            name = "an unnamed condition"
        if (name, where) not in conditions:      # the sentence in the JSON wins over the one in the file
            conditions[(name, where)] = {"name": name, "where": where,
                                         "says": guard["says"] or describe(root, where)}
        return name

    note(initial)
    for name, body in states_doc.items():
        note(name)
        for event, branches in body["on"].items():
            events_of.setdefault(name, []).append(event)
            for raw in branches:
                actions = raw["actions"]
                branch = {"id": raw.get("id"), "target": raw["target"], "guard": condition(raw.get("guard")),
                          "where": raw["where"],
                          "action": ", ".join(actions) if actions else None,
                          "attention": raw["target"] in attention, "never": False}
                outgoing.setdefault(name, []).append((event, branch))
    for moves in list(outgoing.values()):
        for _event, branch in moves:
            note(branch["target"])

    order = [initial]     # the order the program reaches them, nearest first
    for state in order:
        for _event, branch in outgoing.get(state, []):
            if branch["target"] not in order:
                order.append(branch["target"])
    unreachable = [n for n in names if n not in order]
    position = {n: i for i, n in enumerate(order + unreachable)}

    # Shown as the flow first, then the endings: the states that lead somewhere in the
    # order the program reaches them, then the ends that are fine, then the ends that
    # need attention, then anything nothing leads to.
    flow = [n for n in order if n in outgoing]
    endings = [n for n in order if n not in outgoing]
    shown = (flow + [n for n in endings if n not in attention]
             + [n for n in endings if n in attention] + unreachable)
    rank = {n: i for i, n in enumerate(shown)}

    states = []
    for name in shown:
        events = []
        for event in events_of.get(name, []):
            branches = [b for e, b in outgoing[name] if e == event]
            decided = False
            for b in branches:
                b["never"] = decided          # an earlier branch with no condition always wins
                decided = decided or b["guard"] is None
            events.append({"event": event, "branches": branches, "open": not decided})
        states.append({"name": name, "start": name == initial, "end": name not in outgoing,
                       "goal": name == goal, "attention": name in attention,
                       "reachable": name in order, "events": events})

    def reach(start):
        seen, todo = set(), [start]
        while todo:
            for _event, branch in outgoing.get(todo.pop(), []):
                if branch["target"] not in seen:
                    seen.add(branch["target"])
                    todo.append(branch["target"])
        return seen

    reachable_from = {n: reach(n) for n in names}
    wrong, loops = [], []
    for name in shown:
        for event, b in outgoing.get(name, []):
            row = {"source": name, "event": event, "guard": b["guard"], "target": b["target"], "id": b["id"]}
            if b["attention"] and b["target"] != name:
                wrong.append(row)
            back = b["target"] == name or (name in reachable_from[b["target"]]
                                           and position[b["target"]] < position[name])
            if back:
                loops.append(row)

    found = {}            # the states of a route -> how many ways lead along it
    count = {"ways": 0, "steps": 0, "capped": False}

    def walk(state, trail):
        if count["capped"]:
            return
        count["steps"] += 1
        if count["steps"] > STEP_LIMIT:
            count["capped"] = True
            return
        moves = outgoing.get(state)
        if not moves:
            found[tuple(trail)] = found.get(tuple(trail), 0) + 1
            count["ways"] += 1
            if count["ways"] > PATH_LIMIT:
                count["capped"] = True
            return
        for _event, branch in moves:
            if branch["target"] not in trail:
                walk(branch["target"], trail + [branch["target"]])

    walk(initial, [initial])
    paths = [{"states": list(trail), "ways": ways, "end": trail[-1], "attention": trail[-1] in attention}
             for trail, ways in found.items()]
    paths.sort(key=lambda p: (rank[p["end"]], len(p["states"]), p["states"]))

    return {
        "id": doc["id"], "defined_in": doc.get("defined_in") or "", "about": doc.get("about") or "",
        "initial": initial, "goal": goal,
        "states": states, "wrong": wrong, "loops": loops, "paths": paths,
        "path_total": len(paths), "paths_capped": count["capped"],
        "endless": not any(s["end"] and s["reachable"] for s in states),
        "conditions": list(conditions.values()), "unreachable": unreachable,
        "transitions": sum(len(v) for v in outgoing.values()),
        # what notes() needs: what the description itself listed
        "declared": list(states_doc), "extra": doc["extra"], "attention_named": attention,
        "attention_listed": doc["listed_attention"],
        "ids": [(b["id"], b["where"]) for moves in outgoing.values() for _event, b in moves if b["id"]],
    }


def notes(model: dict) -> list:
    """Advice about one description that shape can still show: one sentence for each thing
    a person probably did not mean. shape --check prints them; they refuse nothing."""
    out = []
    names = [s["name"] for s in model["states"]]
    for name in names:
        if name not in model["declared"]:
            out.append('state "%s" is led to but has no entry under "states"; shape shows it as an end' % name)
    for name in model["attention_named"]:
        if name not in names:
            out.append('"attention" names "%s", which is not a state' % name)
    if model["goal"] and model["goal"] not in names:
        out.append('"goal" names "%s", which is not a state' % model["goal"])
    for name in model["unreachable"]:
        out.append('state "%s" is never reached from the start' % name)
    for s in model["states"]:
        for e in s["events"]:
            where = 'state "%s", event "%s"' % (s["name"], e["event"])
            for b in e["branches"]:
                if b["never"]:
                    out.append('%s: the branch to "%s" is never tried, because an earlier branch has no condition'
                               % (where, b["target"]))
            if e["open"]:
                out.append("%s: every branch has a condition, so nothing is declared for when none holds" % where)
    ids = [i for i, _where in model["ids"]]
    for tid in sorted({i for i in ids if ids.count(i) > 1}):
        out.append('the id "%s" is given to more than one branch: %s'
                   % (tid, " and ".join(where for i, where in model["ids"] if i == tid)))
    for c in model["conditions"]:
        if not c["says"]:
            out.append('the condition "%s" has no sentence: give its guard a "says", or its Python function '
                       'a docstring' % c["name"])
    if not model["about"]:
        out.append('it has no "about", the one sentence that says what the program is')
    if not model["attention_listed"]:
        out.append('it has no "attention" list, so shape cannot say which states are the ways it goes wrong')
    return out + list(model["extra"])


# ---- the text ----

def _routes_label(model: dict) -> str:
    if model["paths_capped"]:
        return "more than %d" % PATH_LIMIT
    return str(model["path_total"])


def _target(branch: dict) -> list:
    """The pieces for `→ target`, marked when the target needs attention."""
    pieces = [("→ ", "dim"), (branch["target"], "bad" if branch["attention"] else "target")]
    if branch["attention"]:
        pieces.append((" !", "bad"))
    return pieces


def _move(row: dict) -> str:
    return row["event"] + (" if " + row["guard"] if row["guard"] else "")


def render(model: dict, all_paths: bool = False) -> list:
    """The outline as lines; each line is a list of (text, style) pieces."""
    out = []
    add = out.append
    add([(model["id"], "title"), ("   " + model["defined_in"], "dim")])
    if model["about"]:
        add([(model["about"], None)])
    summary = [plural(len(model["states"]), "state", "states"),
               plural(model["transitions"], "transition", "transitions")]
    if model["endless"]:
        summary.append("no end state")
    else:
        summary.append("%s %s to an end" % (_routes_label(model), "route" if model["path_total"] == 1 else "routes"))
    summary.append(plural(len(model["wrong"]), "way it goes wrong", "ways it goes wrong"))
    add([(", ".join(summary), "dim")])
    if any(s["attention"] for s in model["states"]):
        add([("! marks a state that needs attention", "dim")])
    add([])

    for s in model["states"]:
        tags = [t for t, on in (("start", s["start"]), ("end", s["end"]), ("goal", s["goal"]),
                                ("needs attention", s["attention"]), ("never reached", not s["reachable"])) if on]
        head = [("▶ " if s["start"] else "  ", "target"), (s["name"], "bad" if s["attention"] else "state")]
        head += [(" · " + t, "bad" if t == "needs attention" else "dim") for t in tags]
        add(head)
        for e in s["events"]:
            branches = e["branches"]
            if len(branches) == 1 and branches[0]["guard"] is None:
                line = [("      " + e["event"] + " ", None)] + _target(branches[0])
                if branches[0]["action"]:
                    line.append((" · " + branches[0]["action"], "dim"))
                add(line)
                continue
            add([("      " + e["event"], None)])
            for i, b in enumerate(branches):
                last = i == len(branches) - 1 and not e["open"]
                if b["guard"]:
                    label = "if " + b["guard"]
                else:
                    label = "otherwise" if i else "always"
                line = [("        " + ("└ " if last else "├ "), "dim"), (label + " ", None)] + _target(b)
                if b["action"]:
                    line.append((" · " + b["action"], "dim"))
                if b["never"]:
                    line.append(("   (never tried: an earlier line always wins)", "bad"))
                add(line)
            if e["open"]:
                add([("        └ otherwise no transition is declared", "dim")])
        add([])

    def section(title):
        add([(title, "head")])

    def table(rows, style_last=None):
        if not rows:
            return
        widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
        for r in rows:
            line = [("    ", None)]
            for i, cell in enumerate(r):
                is_last = i == len(r) - 1
                line.append((cell if is_last else cell.ljust(widths[i] + 3),
                             style_last if is_last and style_last else None))
            add(line)

    if model["wrong"]:
        section("Ways it goes wrong (%d)" % len(model["wrong"]))
        table([(w["source"], _move(w), "→ " + w["target"]) for w in model["wrong"]], style_last="bad")
        add([])

    if model["endless"]:
        section("Routes")
        add([("    This program has no end state: it keeps moving between its states.", None)])
        add([])
    else:
        section("Routes from start to an end (%s)" % _routes_label(model))
        if model["paths_capped"]:
            add([("    Counting stopped there; the routes below are the ones found first.", "dim")])
        ends = []
        for p in model["paths"]:
            if p["end"] not in ends:
                ends.append(p["end"])
        for end in ends:
            group = [p for p in model["paths"] if p["end"] == end]
            bad = group[0]["attention"]
            add([("  ends in %s%s" % (end, ", which needs attention" if bad else ""), "bad" if bad else "ok")])
            shown = group if all_paths else group[:PATHS_SHOWN]
            for p in shown:
                line = [("    " + " → ".join(p["states"]), None)]
                if p["ways"] > 1:
                    line.append(("   (%d ways)" % p["ways"], "dim"))
                add(line)
            if len(group) > len(shown):
                add([("    and %d more; shape %s --all prints them" % (len(group) - len(shown), model["id"]), "dim")])
        add([])

    if model["loops"]:
        section("Goes back (%d)" % len(model["loops"]))
        table([(b["source"], _move(b), "→ " + b["target"]) for b in model["loops"]])
        add([])

    if model["conditions"]:
        section("Conditions (%d)" % len(model["conditions"]))
        width = max(len(c["name"]) for c in model["conditions"]) + 3
        for c in model["conditions"]:
            add([("    " + c["name"].ljust(width), "target"), (c["says"] or "(no description written)", None)])
            if c["where"]:
                add([("    " + " " * width + c["where"], "dim")])
        add([])

    if model["unreachable"]:
        section("Never reached (%d)" % len(model["unreachable"]))
        add([("    " + ", ".join(model["unreachable"]), "bad")])
        add([("    Nothing leads to these from the start state.", "dim")])
        add([])

    while out and not out[-1]:
        out.pop()
    return out



# ---- the list ----

def _row(m: dict) -> tuple:
    return (m["id"], str(len(m["states"])), "none" if m["endless"] else _routes_label(m), str(len(m["wrong"])))


def _unread(failures: list) -> list:
    """The lines that say which programs could not be shown."""
    if not failures:
        return []
    out = [[("Could not read %s:" % plural(len(failures), "program or source", "programs or sources"), "bad")]]
    out += [[("    " + f, None)] for f in failures]
    return out + [[]]


def render_list(models: list, above=(), failures=(), flags: str = "") -> list:
    """The printed list: one row per program. `flags` is what must be typed again to see the same
    programs, such as " --file two.json"."""
    out = [line for line in above]
    if above:
        out.append([])
    if models:
        out += screen.table(("PROGRAM", "STATES", "ROUTES", "GOES WRONG", "WHAT IT IS"),
                            [_row(m) + (m["about"] or m["defined_in"],) for m in models])
    else:
        out += [[("No program is listed yet.", None)], []]
    out += _unread(list(failures))
    out.append([("shape NAME%s opens one; part of a name is enough." % flags, "dim")])
    return out


# ---- where the JSON comes from ----

def find_sources(home: str, cwd: str, file=None, config=None, environ=None):
    """(root, sources, above, flags): the folder that paths and commands start from, the list
    of sources, lines to show above the list, and the flags to type again to see the same list.

    --file names one JSON file, or - for standard input. Otherwise the list is --config, or $SHAPE_CONFIG, or the
    shape.json in the folder shape was typed in or the nearest folder above it. When there
    is none, the examples in shape's own folder are shown, and the lines above say so."""
    environ = os.environ if environ is None else environ
    if file == "-":
        return os.path.abspath(cwd), [{"stdin": True}], [], " --file -"
    if file:
        path = os.path.abspath(os.path.join(cwd, file))
        return os.path.dirname(path), [{"file": os.path.basename(path)}], [], " --file " + file
    if config:
        path = os.path.abspath(os.path.join(cwd, config))
        return os.path.dirname(path), screen.sources(path), [], " --config " + config
    if environ.get("SHAPE_CONFIG"):
        path = os.path.abspath(os.path.join(cwd, environ["SHAPE_CONFIG"]))
        return os.path.dirname(path), screen.sources(path), [], ""
    folder = os.path.abspath(cwd)
    while True:
        path = os.path.join(folder, CONFIG)
        if os.path.isfile(path):
            return folder, _guarded(path, screen.sources(path)), [], ""
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    root = os.path.join(home, "examples")
    above = [[("These are the examples that come with shape.", None)],
             [("No %s was found in this folder or in a folder above it. %s says how to list your own programs."
               % (CONFIG, os.path.join(home, "docs", "PLUG-IN.md")), "dim")]]
    return root, screen.sources(os.path.join(root, CONFIG)), above, ""


def _distrust(path: str) -> str:
    """Why the commands in the shape.json at `path` may not run, or "" when they may. A shape.json
    that shape finds by itself must belong to the person running shape, and nobody else may be
    able to change it. One named with --config or SHAPE_CONFIG is trusted."""
    try:
        infos = (os.lstat(path), os.stat(path))
    except (OSError, ValueError):
        return ""
    if hasattr(os, "getuid") and any(info.st_uid != os.getuid() for info in infos):
        return "%s belongs to another user" % path
    if infos[1].st_mode & 0o002:
        return "anyone on this computer can change %s" % path
    return ""


def _guarded(path: str, sources: list) -> list:
    """The sources of the shape.json at `path`, with each command refused when that file is not trusted."""
    why = _distrust(path)
    if not why:
        return sources
    sentence = ("shape did not run this command, because %s. If you trust that file, shape --config %s runs it."
                % (why, shlex.quote(path)))
    return [screen.Refused(src, sentence) if isinstance(src, dict) and "command" in src else src for src in sources]


def _read(root: str, src) -> tuple:
    """(label, [descriptions]) for one source. A source gives one description, a list of
    them or {"machines": [...]}. Its optional "registry" names a JSON list of
    {id, path, attention, about}, which fills in what a description does not say itself."""
    if not isinstance(src, dict):
        raise SourceError('a source is an object with "file" or "command", and this is %s' % json.dumps(src))
    label, data = screen.read_source(root, src)
    if isinstance(data, dict) and "machines" in data:
        data = data["machines"]
    found = data if isinstance(data, list) else [data]
    extra = {}
    if src.get("registry"):
        _label, entries = screen.read_source(root, {"file": src["registry"]})
        extra = {e["id"]: e for e in (entries if isinstance(entries, list) else [])
                 if isinstance(e, dict) and isinstance(e.get("id"), str)}
    for doc in found:
        if not isinstance(doc, dict):
            continue
        entry = extra.get(doc["id"], {}) if isinstance(doc.get("id"), str) else {}
        if "attention" not in doc and "attention" in entry:
            doc["attention"] = entry["attention"]
        if entry.get("path") and not doc.get("defined_in"):
            doc["defined_in"] = entry["path"]
        if entry.get("about") and not doc.get("about"):
            doc["about"] = entry["about"]
    return label, found


def _named(doc) -> bool:
    return isinstance(doc, dict) and isinstance(doc.get("id"), str) and bool(doc["id"])


def load_docs(root: str, sources: list) -> list:
    """Every description the sources give, in order. The first thing wrong raises SourceError."""
    docs, seen = [], {}
    for src in sources:
        label, found = _read(root, src)
        for doc in found:
            if not _named(doc):
                raise SourceError("%s: an entry is not a machine description" % label)
            if doc["id"] in seen:
                raise SourceError("%s is described twice: by %s and by %s" % (doc["id"], seen[doc["id"]], label))
            seen[doc["id"]] = label
            docs.append(doc)
    return docs


def load_all(root: str, sources: list) -> tuple:
    """(descriptions, failures): like load_docs, but a source that cannot be read becomes a
    sentence in failures and the rest are still read, so one broken program does not hide
    the others."""
    docs, failures, seen = [], [], {}
    for src in sources:
        try:
            label, found = _read(root, src)
        except SourceError as exc:
            failures.append(str(exc))
            continue
        for doc in found:
            if not _named(doc):
                try:
                    shapeformat.read(doc)
                    why = "an entry is not a machine description"
                except FormatError as exc:
                    why = "; ".join(exc.problems)
                failures.append("%s: %s" % (label, why))
            elif doc["id"] in seen:
                failures.append("%s is described twice: by %s and by %s" % (doc["id"], seen[doc["id"]], label))
            else:
                seen[doc["id"]] = label
                docs.append(doc)
    return docs, failures


# ---- shape --check ----

def check(root: str, sources: list, wanted=None) -> tuple:
    """(lines, exit code): every program's JSON read strictly. A problem is something shape
    cannot show, and makes the exit code 1. A note is advice, and changes nothing."""
    rows, unread, seen = [], [], {}
    for src in sources:
        try:
            label, found = _read(root, src)
        except SourceError as exc:
            unread.append(str(exc))
            continue
        for doc in found:
            name = doc["id"] if _named(doc) else "(an entry of %s)" % label
            if wanted and wanted.lower() not in name.lower():
                continue
            problems, advice, size = [], [], ""
            try:
                model = build(doc, root)
                advice = notes(model)
                size = "%s, %s" % (plural(len(model["states"]), "state", "states"),
                                   plural(model["transitions"], "transition", "transitions"))
            except FormatError as exc:
                problems = list(exc.problems)
            if name in seen:
                problems.append("it is described twice: by %s and by %s" % (seen[name], label))
            seen[name] = label
            rows.append((name, problems, advice, size))

    if wanted and not rows:
        return [], 2
    out = []
    width = max([len(r[0]) for r in rows] + [0])
    for name, problems, advice, size in rows:
        if problems:
            verdict, style = plural(len(problems), "problem", "problems"), "bad"
        else:
            verdict, style = "ok" + (", " + plural(len(advice), "note", "notes") if advice else ""), "ok"
        out.append([(name.ljust(width + 3), "state"), (verdict.ljust(14), style), (size, "dim")])
        out += [[("    problem: ", "bad"), (p, None)] for p in problems]
        out += [[("    note: ", "dim"), (n, None)] for n in advice]
    out += [[("could not read: ", "bad"), (u, None)] for u in unread]
    broken = sum(1 for r in rows if r[1])
    if rows or unread:
        out.append([])
    noted = sum(len(r[2]) for r in rows)
    summary = "%s checked: " % plural(len(rows), "program", "programs")
    if not rows:
        summary = "No program was checked."
    elif not broken and noted:
        summary += "no problems, and %s." % plural(noted, "note", "notes")
    elif not broken:
        summary += "all are fine." if len(rows) != 1 else "it is fine."
    else:
        summary += "%d %s fine and %d %s." % (len(rows) - broken, "is" if len(rows) - broken == 1 else "are",
                                               broken, "has problems" if broken == 1 else "have problems")
    if unread:
        summary += " %s could not be read." % plural(len(unread), "source", "sources")
    out.append([(summary, None)])
    return out, 1 if broken or unread else 0


# ---- the screen that stays open ----

HELP = [
    [("How to read this", "title")],
    [],
    [("A program is shown as the situations it can be in. Each one is called a state.", None)],
    [("Under a state are the things that can happen there, and where each one leads.", None)],
    [],
    [("▶ ", "target"), ("idle", "state"), (" · start", "dim"), ("              the state the program starts in", "dim")],
    [("      start ", None), ("→ ", "dim"), ("checking", "target"), ("        when \"start\" happens it moves to \"checking\"", "dim")],
    [("      error", None), ("                   one thing that can happen, with several outcomes:", "dim")],
    [("        ├ ", "dim"), ("if is_auth ", None), ("→ ", "dim"), ("auth", "bad"), (" !", "bad"), ("     the first line whose \"if\" is true wins", "dim")],
    [("        └ ", "dim"), ("otherwise ", None), ("→ ", "dim"), ("failed", "bad"), (" !", "bad"), ("    and this one when none is", "dim")],
    [("  ", None), ("ok", "state"), (" · end", "dim"), ("                  a state where the program stops", "dim")],
    [],
    [("! and red mark a state that needs attention, usually a failure.", None)],
    [],
    [("Below the states there are lists:", None)],
    [("  Ways it goes wrong   ", "head"), ("every move into a state that needs attention", None)],
    [("  Routes               ", "head"), ("every way from the start to an end", None)],
    [("  Goes back            ", "head"), ("every move that returns to an earlier state, such as a retry", None)],
    [("  Conditions           ", "head"), ("what each \"if\" means, in the words written in the program", None)],
    [],
    [("Nothing here runs or changes a program. It only shows how each one is written.", None)],
]


class Browser(screen.Browser):
    """The open screen for programs: the list, one program's outline, the help."""

    name = "shape"
    tagline = "what each program does, without reading its code"
    head = ("PROGRAM", "STATES", "ROUTES", "GOES WRONG")
    help_lines = HELP

    def row(self, model: dict) -> tuple:
        return _row(model)

    def picked(self, model: dict) -> list:
        return [[(model["about"] or "No sentence has been written for this program yet.", None)],
                [(model["defined_in"], "dim")]]

    def outline(self, model: dict, more: bool) -> list:
        return render(model, all_paths=more)

    def more_key(self, more: bool) -> str:
        return "a %s routes" % ("fewer" if more else "all")


# ---- the command ----

def main(argv=None, home: str = "", cwd=None, environ=None) -> int:
    """The shape command. `home` is shape's own folder, where its examples and docs are."""
    ap = argparse.ArgumentParser(
        prog="shape",
        description="See the shape of a program: its states, every route through it and every way it goes wrong.",
        epilog="The programs are the ones listed in the shape.json of this folder or a folder above it. "
               "docs/PLUG-IN.md in shape's folder says how to add one.")
    ap.add_argument("name", nargs="?", help="a program, or part of its name (default: list them all)")
    ap.add_argument("--all", action="store_true", help="print every route, however many there are")
    ap.add_argument("--plain", action="store_true", help="print the text and exit, instead of opening the screen")
    ap.add_argument("--check", action="store_true",
                    help="check the JSON of every program, or of the named one, and say what is wrong")
    ap.add_argument("--file", metavar="PATH",
                    help="read this one JSON file instead of the programs in shape.json; - reads standard input")
    ap.add_argument("--config", metavar="PATH", help="use this list of programs instead of the shape.json found from here")
    ap.add_argument("--version", action="version", version="shape " + VERSION)
    args = ap.parse_args(argv)

    def fail(*sentences, code=1):
        for s in sentences:
            print("shape: %s" % s, file=sys.stderr)
        return code

    try:
        root, sources, above, flags = find_sources(home, cwd or os.getcwd(), args.file, args.config, environ)
    except SourceError as exc:
        return fail(str(exc))

    if args.check:
        lines, code = check(root, sources, args.name)
        if code == 2:
            return fail("nothing is called %r, so nothing was checked" % args.name, code=2)
        sys.stdout.write(screen.to_text(lines, color=False))
        return code

    docs, failures = load_all(root, sources)
    if args.file and failures and not docs:
        return fail(*failures)      # the one file that was asked for could not be read
    ids = [d["id"] for d in docs]
    live = sys.stdout.isatty() and sys.stdin.isatty() and not args.plain

    picked = None
    if args.name is None and args.file and len(ids) == 1 and not failures:
        args.name = ids[0]          # one file that holds one program: open on it
    if args.name is not None:
        wanted = args.name.lower()
        hits = [i for i in ids if i.lower() == wanted] or [i for i in ids if wanted in i.lower()]
        if len(hits) > 1:
            return fail("%r fits %d names: %s" % (args.name, len(hits), ", ".join(hits)), code=2)
        if not hits:
            said = ["nothing is called %r" % args.name, "the programs are: %s" % (", ".join(ids) or "(none)")]
            if failures:
                said.append("%s could not be read; shape --check%s says why"
                            % (plural(len(failures), "program or source", "programs or sources"), flags))
            if above:
                said.append("these are the examples that come with shape, because no %s was found from this "
                            "folder up; shape --file PATH reads one JSON file" % CONFIG)
            return fail(*said, code=2)
        picked = hits[0]
        try:
            model = build(docs[ids.index(picked)], root)
        except FormatError as exc:
            return fail("%s cannot be shown, because its JSON has %s:"
                        % (exc.id, plural(len(exc.problems), "problem", "problems")),
                        *["    " + p for p in exc.problems])
        if not live:
            sys.stdout.write(screen.to_text(render(model, all_paths=args.all), color=False))
            return 0

    models = []
    for doc in docs:
        try:
            models.append(build(doc, root))
        except FormatError as exc:
            failures.append("%s: its JSON has %s; shape --check%s lists them"
                            % (exc.id, plural(len(exc.problems), "problem", "problems"), flags))
    if not live:
        sys.stdout.write(screen.to_text(render_list(models, above, failures, flags), color=False))
        return 0
    start = [m["id"] for m in models].index(picked) if picked else None
    browser = Browser(models, start=start, more=args.all)
    browser.above, browser.below = above, _unread(failures)
    return screen.browse(browser)
