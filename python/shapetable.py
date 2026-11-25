"""shapetable: keep a program's moves in one table, run through the table, print it for shape.

Copy this one file into your project. It needs nothing but Python 3.9 or later.

    from shapetable import Machine, T

    def is_declined(order):
        '''The bank refused the card.'''
        return order["card"] == "declined"

    MACHINE = Machine("orders.fulfil", initial="new", goal="shipped",
                      about="Takes one order from payment to the door.",
                      attention=["declined", "failed"], transitions=[
        T("submit",   "new",    "submitted", "paying"),
        T("declined", "paying", "error",     "declined", guard=is_declined),
        T("failed",   "paying", "error",     "failed"),
        T("paid",     "paying", "paid",      "shipped"),
    ])

    move = MACHINE.step(state, event, order)   # the move the table gives for this state and event
    state = move.target                        # the program goes where the table says

    MACHINE.print_json()                       # the same table as JSON, which is what shape reads

The moves for one state and event are tried in the order they are written. The first one
whose guard holds, or that has no guard, is taken. Because the program takes its moves from
the table that is printed, what shape shows is what the program does.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Optional

__version__ = "0.1.0"


class NoTransition(Exception):
    """The state has no move for the event, or every guard said no."""


class T:
    """One move: in the state `source`, on `event`, go to `target`. A guard is a function of the
    context that says whether this move applies; an output is a name for what the move does."""

    __slots__ = ("id", "source", "event", "target", "guard", "output")

    def __init__(self, id: str, source: str, event: str, target: str,
                 guard: Optional[Callable[[Any], bool]] = None, output: Optional[str] = None):
        self.id, self.source, self.event, self.target = id, source, event, target
        self.guard, self.output = guard, output


def _relative(path: str) -> str:
    """The path from the folder the program was started in, when the file is inside it."""
    path, here = os.path.abspath(path), os.getcwd()
    return os.path.relpath(path, here) if path.startswith(here + os.sep) else path


def _guard_json(fn: Callable) -> dict:
    entry = {"name": getattr(fn, "__name__", "a condition")}
    code = getattr(fn, "__code__", None)
    if code is not None:
        entry["source"] = "%s:%d" % (_relative(code.co_filename), code.co_firstlineno)
    says = " ".join((getattr(fn, "__doc__", None) or "").strip().split("\n\n", 1)[0].split())
    if says:
        entry["says"] = says
    return entry


class Machine:
    """A table of moves with a name. `about` is one sentence that says what the program is,
    `attention` lists the states a person should look at (a failure, usually), and `goal` is
    the state the program is meant to reach."""

    def __init__(self, id: str, initial: str, transitions: list, goal: Optional[str] = None,
                 about: str = "", attention=(), defined_in: Optional[str] = None):
        self.id, self.initial, self.transitions = id, initial, list(transitions)
        self.goal, self.about, self.attention = goal, about, list(attention)
        self.defined_in = defined_in or _relative(sys._getframe(1).f_code.co_filename)
        ids = [t.id for t in self.transitions]
        twice = sorted({i for i in ids if ids.count(i) > 1})
        if twice:
            raise ValueError("%s: these move ids are used twice: %s" % (id, ", ".join(twice)))
        self.states = []
        for t in self.transitions:
            for s in (t.source, t.target):
                if s not in self.states:
                    self.states.append(s)
        for what, names in (("start state", [initial]), ("goal", [goal] if goal is not None else []),
                            ("attention state", self.attention)):
            for name in names:
                if name not in self.states:
                    raise ValueError("%s: the %s %r is not in any move" % (id, what, name))

    def step(self, state: str, event: str, ctx: Any = None) -> T:
        """The move to take from `state` on `event`. The program then goes to its target."""
        for t in self.transitions:
            if t.source == state and t.event == event and (t.guard is None or t.guard(ctx)):
                return t
        raise NoTransition("%s: no move from %r on %r" % (self.id, state, event))

    def to_json(self) -> dict:
        """The table in shape's format: states, then the events of each, then the branches in order."""
        states = {s: {"on": {}} for s in self.states}
        for t in self.transitions:
            entry = {"id": t.id, "target": t.target}
            if t.guard is not None:
                entry["guard"] = _guard_json(t.guard)
            if t.output is not None:
                entry["actions"] = [t.output]
            states[t.source]["on"].setdefault(t.event, []).append(entry)
        doc = {"id": self.id, "about": self.about, "defined_in": self.defined_in, "initial": self.initial}
        if self.goal is not None:
            doc["goal"] = self.goal
        doc["attention"] = list(self.attention)
        doc["states"] = states
        return doc

    def print_json(self, out=None) -> None:
        json.dump(self.to_json(), out or sys.stdout, indent=2)
        (out or sys.stdout).write("\n")


def dump(machines: list, out=None) -> None:
    """Print several tables as one JSON document, for a program that has more than one."""
    json.dump({"machines": [m.to_json() for m in machines]}, out or sys.stdout, indent=2)
    (out or sys.stdout).write("\n")
