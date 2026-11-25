"""shapeformat: the JSON a program gives shape, read strictly.

read() takes one description and returns it with every shorthand written out, so the
rest of shape sees one form only. When the description is wrong it raises FormatError,
which carries every problem found, each in words that name the state and the event.
docs/FORMAT.md describes the format for a person; this file is the format as code.
Standard library only, Python 3.9 compatible.
"""
from __future__ import annotations

KEYS = ("id", "initial", "states", "goal", "attention", "about", "defined_in", "$schema")
STATE_LIMIT = 2000      # the most states one description may name
BRANCH_LIMIT = 20000    # and the most branches it may have
STATE_KEYS = ("on",)
BRANCH_KEYS = ("id", "target", "guard", "actions")
GUARD_KEYS = ("name", "source", "says")


class FormatError(ValueError):
    """A description that shape cannot show. problems holds one sentence for each fault."""

    def __init__(self, id: str, problems: list):
        self.id, self.problems = id, list(problems)
        ValueError.__init__(self, "%s: %s" % (id, "; ".join(self.problems)))


def _kind(value) -> str:
    if isinstance(value, bool):
        return "true or false"
    if value == "":
        return "an empty string"
    return {dict: "an object", list: "a list", str: "a string", type(None): "null"}.get(type(value), "a number")


def _text(value) -> bool:
    return isinstance(value, str) and bool(value)


def _guard(raw, where: str, say, extra):
    """A condition as {"name", "source", "says"}, or None when the branch has none."""
    if raw is None:
        return None
    if _text(raw):
        return {"name": raw, "source": "", "says": ""}
    if not isinstance(raw, dict):
        say('%s: its guard is %s, and it should be a name or an object such as {"name": "is_full"}'
            % (where, _kind(raw)))
        return None
    if not _text(raw.get("name")):
        say('%s: its guard has no "name"' % where)
        return None
    guard = {"name": raw["name"], "source": "", "says": ""}
    extra += ['%s: the guard has a key shape does not read: "%s"' % (where, k) for k in raw if k not in GUARD_KEYS]
    for key in ("source", "says"):
        if raw.get(key) is None:
            continue
        if not isinstance(raw[key], str):
            say('%s: the "%s" of its guard is %s, and it should be a string' % (where, key, _kind(raw[key])))
        else:
            guard[key] = raw[key]
    return guard


def _branch(raw, where: str, say, extra):
    """One branch as {"id", "target", "guard", "actions", "where"}, or None when it cannot be read."""
    if _text(raw):
        return {"id": None, "target": raw, "guard": None, "actions": [], "where": where}
    if not isinstance(raw, dict):
        say('%s: it is %s, and it should be the name of a state or an object such as {"target": "done"}'
            % (where, _kind(raw)))
        return None
    if not _text(raw.get("target")):
        say('%s: it has no "target" (the state this leads to)' % where)
        return None
    actions = raw.get("actions")
    if actions is None:
        actions = []
    elif _text(actions):
        actions = [actions]
    elif not isinstance(actions, list) or not all(_text(a) for a in actions):
        say('%s: "actions" should be a name or a list of names' % where)
        actions = []
    tid = raw.get("id")
    if tid is not None and not _text(tid):
        say('%s: its "id" is %s, and it should be a string that is not empty' % (where, _kind(tid)))
        tid = None
    extra += ['%s: the branch has a key shape does not read: "%s"' % (where, k) for k in raw if k not in BRANCH_KEYS]
    return {"id": tid, "target": raw["target"], "guard": _guard(raw.get("guard"), where, say, extra),
            "actions": list(actions), "where": where}


def read(doc) -> dict:
    """One description with every shorthand written out:

        {"id", "initial", "states": {name: {"on": {event: [branch, ...]}}},
         "goal", "attention": [...], "about", "defined_in",
         "extra": [a sentence for each key shape does not read]}

    where a branch is {"id", "target", "guard": None or {"name", "source", "says"}, "actions": [...],
    "where": the words that name its state and event}.
    Raises FormatError with every problem when the description is wrong."""
    if not isinstance(doc, dict):
        raise FormatError("(no id)", ["a description is a JSON object, and this is %s" % _kind(doc)])
    problems = []
    say = problems.append
    extra = ['it has a key shape does not read: "%s"' % k for k in doc if k not in KEYS]

    name = doc.get("id")
    if not _text(name):
        say('it has no "id" (the name shape lists the program under)')
        name = "(no id)"
    initial = doc.get("initial")
    if not _text(initial):
        say('it has no "initial" (the state the program starts in)')
        initial = None

    raw_states = doc.get("states")
    if not isinstance(raw_states, dict) or not raw_states:
        say('it has no "states" (an object with one entry for each state)')
        raw_states = {}
    states = {}
    for state, body in raw_states.items():
        if body is None:
            body = {}
        if not isinstance(body, dict):
            say('state "%s": its entry is %s, and it should be an object such as {"on": {...}} or {}'
                % (state, _kind(body)))
            body = {}
        extra += ['state "%s" has a key shape does not read: "%s"' % (state, k) for k in body if k not in STATE_KEYS]
        events = body.get("on")
        if events is None:
            events = {}
        if not isinstance(events, dict):
            say('state "%s": "on" is %s, and it should be an object with one entry for each event'
                % (state, _kind(events)))
            events = {}
        on = {}
        for event, value in events.items():
            where = 'state "%s", event "%s"' % (state, event)
            raws = value if isinstance(value, list) else [value]
            if not raws:
                say("%s: it lists no branch" % where)
            found = []
            for n, raw in enumerate(raws, start=1):
                branch = _branch(raw, where + (", branch %d" % n if len(raws) > 1 else ""), say, extra)
                if branch:
                    found.append(branch)
            if found:
                on[event] = found
        states[state] = {"on": on}
    if initial and states and initial not in states:
        say('the start state "%s" is not one of its states' % initial)
    branches = [b for body in states.values() for found in body["on"].values() for b in found]
    named = len(set(states) | {b["target"] for b in branches})
    if named > STATE_LIMIT:
        say("it names {:,} states, and a description may name at most {:,}".format(named, STATE_LIMIT))
    if len(branches) > BRANCH_LIMIT:
        say("it has {:,} branches, and a description may have at most {:,}".format(len(branches), BRANCH_LIMIT))

    goal = doc.get("goal")
    if goal is not None and not _text(goal):
        say('"goal" is %s, and it should be the name of one state' % _kind(goal))
        goal = None
    attention = doc.get("attention")
    if attention is None:
        attention = []
    elif not isinstance(attention, list) or not all(_text(a) for a in attention):
        say('"attention" should be a list of state names, such as ["failed"]')
        attention = []
    texts = {}
    for key in ("about", "defined_in"):
        texts[key] = doc.get(key)
        if texts[key] is not None and not isinstance(texts[key], str):
            say('"%s" is %s, and it should be a string' % (key, _kind(texts[key])))
            texts[key] = None

    if problems:
        raise FormatError(name, problems)
    return {"id": name, "initial": initial, "states": states, "goal": goal, "attention": list(attention),
            "about": texts["about"] or "", "defined_in": texts["defined_in"] or "",
            "listed_attention": doc.get("attention") is not None,
            "extra": extra}
