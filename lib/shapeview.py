"""shapeview: a program's state machine as an outline a person can read.

The input is JSON: the description a program prints of the machine it runs
(states, the events each state takes, and for each event its ordered branches).
build() turns one description into a plain model: the states in the order the
program reaches them, every way into a state that needs attention, every route
from the start to an end, the transitions that go back, and the conditions.
render() turns the model into lines of (text, style) pieces, so everything can be
tested without a terminal.

Where the JSON comes from is listed in shape.json (see load_docs). The screen that
stays open, the printed list and the command line are in screen.py. Standard library
only, Python 3.9 compatible.
"""
from __future__ import annotations

import ast
import os

import screen
from screen import SourceError, plural

SOURCES = "shape.json"

PATH_LIMIT = 2000      # stop counting routes past this many; the outline says so
STEP_LIMIT = 200000    # and stop walking after this many steps, whatever was found
PATHS_SHOWN = 8        # routes printed for one end state unless --all is given


# ---- the words written beside a condition ----

_parsed = {}


def describe(root: str, where: str) -> str:
    """The first paragraph of the docstring of the Python function at `file:line`,
    or "" when the file is not there, is not Python, or the function has none.
    The file is parsed, never run."""
    path, _, line = (where or "").rpartition(":")
    if not root or not path.endswith(".py") or not line.isdigit():
        return ""
    full = os.path.join(root, path)
    if full not in _parsed:
        try:
            with open(full, encoding="utf-8") as fh:
                _parsed[full] = ast.parse(fh.read())
        except (OSError, SyntaxError, ValueError):
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
    """The outline model of one machine description."""
    for key in ("id", "initial", "states"):
        if key not in doc:
            raise ValueError("not a machine description: no %r" % key)
    initial, states_doc = doc["initial"], doc["states"]
    attention = list(doc.get("attention") or [])
    goal = doc.get("goal")

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
        if isinstance(guard, dict):
            name, where = guard.get("name") or "a condition", guard.get("source") or ""
        else:
            name, where = str(guard), ""
        if name == "<lambda>":
            name = "an unnamed condition"
        conditions.setdefault((name, where), {"name": name, "where": where, "says": describe(root, where)})
        return name

    note(initial)
    for name, body in states_doc.items():
        note(name)
        for event, branches in ((body or {}).get("on") or {}).items():
            events_of.setdefault(name, []).append(event)
            for raw in branches:
                actions = raw.get("actions") or []
                branch = {"id": raw.get("id"), "target": raw["target"], "guard": condition(raw.get("guard")),
                          "action": ", ".join(actions) if actions else None,
                          "attention": raw["target"] in attention, "never": False}
                outgoing.setdefault(name, []).append((event, branch))
    for moves in list(outgoing.values()):
        for _event, branch in moves:
            note(branch["target"])
    if initial not in states_doc and initial not in outgoing:
        raise ValueError("%s: the start state %r is not one of its states" % (doc["id"], initial))

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
    }


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


def render_list(models: list) -> list:
    """The printed list: one row per program."""
    out = []
    if models:
        out = screen.table(("PROGRAM", "STATES", "ROUTES", "GOES WRONG", "WHAT IT IS"),
                           [_row(m) + (m["about"] or m["defined_in"],) for m in models])
    out.append([("shape NAME opens one; part of a name is enough.", "dim")])
    return out


# ---- where the JSON comes from ----

def load_docs(root: str) -> list:
    """Every machine description named by shape.json, in order.

    A source is {"file": PATH} or {"command": [ARGV...]}; either gives one machine,
    a list of machines or {"machines": [...]}. An optional "registry": PATH names a
    JSON list of {id, path, attention, about}; it fills in a machine's file, the
    states that need attention and the sentence that says what the program is, when
    the description itself does not say."""
    docs, seen = [], {}
    for src in screen.sources(root, SOURCES):
        label, data = screen.read_source(root, src)
        if isinstance(data, dict) and "machines" in data:
            data = data["machines"]
        found = data if isinstance(data, list) else [data]
        extra = {}
        if src.get("registry"):
            _label, entries = screen.read_source(root, {"file": src["registry"]})
            extra = {e["id"]: e for e in entries if isinstance(e, dict) and "id" in e}
        for doc in found:
            if not isinstance(doc, dict) or "id" not in doc:
                raise SourceError("%s: an entry is not a machine description" % label)
            if doc["id"] in seen:
                raise SourceError("%s is described twice: by %s and by %s" % (doc["id"], seen[doc["id"]], label))
            seen[doc["id"]] = label
            entry = extra.get(doc["id"], {})
            if "attention" not in doc and "attention" in entry:
                doc["attention"] = entry["attention"]
            if not doc.get("defined_in") and entry.get("path"):
                doc["defined_in"] = entry["path"]
            if not doc.get("about") and entry.get("about"):
                doc["about"] = entry["about"]
            docs.append(doc)
    return docs


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

def main(argv=None, root: str = "") -> int:
    return screen.command(
        argv, prog="shape",
        description="See the shape of a program: its states, every route through it and every way it goes wrong.",
        one="a program", many="programs", all_help="print every route, however many there are",
        elsewhere="",
        load=lambda: [(d["id"], lambda d=d: build(d, root)) for d in load_docs(root)],
        render_list=render_list, render_one=lambda model, more: render(model, all_paths=more), browser=Browser)
