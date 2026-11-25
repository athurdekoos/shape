# Show your own program in shape

`shape` does not read your source code. It reads a description of your program in JSON:
the states the program can be in, the events that can happen in each state, and where
each event leads. This page shows three ways to produce that JSON, from the quickest to
the one you can trust, and then how to tell `shape` where to find it.

The words used here:

| Word | What it means |
|---|---|
| State | A situation the program can be in, such as `paying` or `failed`. |
| Event | Something that happens in a state, such as `paid` or `error`. |
| Move | One line of the table: in this state, on this event, go to that state. |
| Condition | A yes-or-no question that picks between two moves for the same event. The JSON calls it a guard. |
| Table | The list of all the moves. |

## Way 1: write a JSON file

Write the states and events by hand. This takes a few minutes, and it works for a program
you cannot change.

```json
{
  "id": "door",
  "about": "A door that opens when pushed, unless it is jammed.",
  "initial": "closed",
  "attention": ["stuck"],
  "states": {
    "closed": {"on": {"push": "open", "jam": "stuck"}},
    "open": {"on": {"pull": "closed"}},
    "stuck": {}
  }
}
```

Save it as `door.json` and look at it:

```bash
shape --file door.json
shape --check --file door.json
```

[examples/coffee/coffee.json](../examples/coffee/coffee.json) is a longer file of this kind,
with a condition and a retry.

The weakness of this way is that nothing ties the file to the code. When the code changes
and the file does not, the outline is wrong and nothing says so.

## Way 2: have the program print the JSON

Keep the moves as a table in the program's own code, and add a flag that prints the table
as JSON. `shape` runs the command each time it opens, so the outline is never older than
the code.

In Python, copy [python/shapetable.py](../python/shapetable.py) into your project. It is
one file and needs nothing else.

```python
import sys
from shapetable import Machine, T

def is_declined(order):
    """The bank refused the card."""
    return order["card"] == "declined"

MACHINE = Machine(
    "orders.fulfil", initial="new", goal="shipped",
    about="Takes one order from the basket to the door.",
    attention=["declined", "failed"],
    transitions=[
        T("submit",     "new",    "submitted", "paying"),
        T("paid",       "paying", "paid",      "shipped"),
        T("declined",   "paying", "error",     "declined", guard=is_declined),
        T("pay_failed", "paying", "error",     "failed"),
    ])

if "--shape" in sys.argv:
    MACHINE.print_json()
    sys.exit(0)
```

Each `T` line is one move: its name, the state it starts in, the event, and the state it
leads to. A `guard` is a function that answers yes or no. The first sentence of its
docstring is what `shape` prints beside the condition.

In another language, build the same JSON from a table of your own.
[examples/download/download.js](../examples/download/download.js) does it in JavaScript in
about fifteen lines, with no library. [FORMAT.md](FORMAT.md) describes every key.

A program with more than one table prints them together as `{"machines": [...]}`. In Python
that is `shapetable.dump([FIRST, SECOND])`.

## Way 3: make the table the program

Way 2 still allows the code to do one thing while the table says another. The last step is
to make the program take every move by looking it up in the table.

```python
def fulfil(order):
    state = MACHINE.initial
    while state in WORK:
        event = WORK[state](order)                 # do the work of this state, and say what happened
        move = MACHINE.step(state, event, order)   # the table says where that leads
        state = move.target
    return state
```

`WORK` maps each state to the function that does that state's work and returns an event.
The program never writes the name of the next state anywhere but the table. Now the JSON
that `--shape` prints is the program, not a description of it.
[examples/orders/orders.py](../examples/orders/orders.py) is this program in full.

Keep it that way with a test. The one in
[tests/test_examples.py](../tests/test_examples.py) runs the example, reads every move it
prints, and fails when a move is not in the table. A second test reads the code and fails
when the state is set from anywhere but the table.

## Tell shape where your programs are

Put a file called `shape.json` at the top of your project. It is a list of sources, and a
source is either a file or a command.

```json
[
  {"command": ["python3", "orders.py", "--shape"]},
  {"command": ["node", "tools/download.js", "--shape"]},
  {"file": "docs/door.json"}
]
```

- Paths start from the folder that holds `shape.json`, and commands run in that folder.
- A command is a list of words. It is not passed through a shell.
- A command has 60 seconds to print its JSON.
- `shape` finds the file from any folder inside the project, the way `git` finds its folder.

`shape` runs the commands in `shape.json` each time it opens. List only commands that print
and do nothing else, and read a `shape.json` you did not write before you type `shape` in
its project.

## Check it

```bash
shape --check
```

A problem is something `shape` cannot show, such as a branch with no target. A note is
advice about something you probably did not mean, such as a state nothing leads to. The
command exits with 1 when there is a problem, so it can run in your tests.

You are done when these four things are true:

1. `shape --check` reports no problem and no note.
2. Every state a person should look at is in `attention`.
3. Every condition has a sentence.
4. Someone who has not read the code can say, from the outline, what the program does when
   something fails.

## Turning an existing program into a table

1. Find the part that moves through steps: a job, a sync, an order, a request, an upload.
2. List the situations it can be in. A good state name answers "what is it doing now?" or
   "how did it end?".
3. For each state, list what can happen there. Those are the events. Name them for what
   happened (`paid`, `error`, `timed_out`), not for what to do next.
4. Where one event can lead to two states, write the question that decides it as a small
   function with one sentence of description. That is a condition.
5. Mark the states a person should look at, usually the failures.
6. Change the code so that it takes its moves from the table, one state at a time, and run
   the program's own tests after each change.

Start with one part of the program. A table of six states that is true is worth more than
a table of sixty that is a guess.
