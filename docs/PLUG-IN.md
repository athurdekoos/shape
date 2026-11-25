# Show your own program in shape

`shape` does not read your source code. It reads a description of your program in JSON:
the states the program can be in, the events that can happen in each state, and where
each event leads. This page shows three ways to produce that JSON, from the quickest to
the one you can trust. Then it shows how to tell `shape` where to find it.

These are the words this page and the outline use:

| Word | What it means |
|---|---|
| State | A situation the program can be in, such as `paying` or `failed`. |
| Event | Something that happens in a state, such as `paid` or `error`. |
| Move | One line of the table: in this state, on this event, go to that state. |
| Transition | The word the screen uses for a move. |
| Branch | One possible outcome of an event. An event has one branch, or several that are tried in order. |
| Condition | A yes-or-no question that picks between two branches of the same event. The JSON calls it a guard. |
| Action | A name for what a move does on the way, such as `print_label`. The outline shows it after the target. |
| Table | The list of all the moves. |
| End | A state with no events. The program stops there. |
| Goal | The end the program is meant to reach. The outline marks it with the word goal. |
| Route | A way from the start state to an end that visits no state twice. |

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

The first command opens the outline of the door straight away, because the file holds one
program. The second command checks the file. It ends with "it is fine" when it finds no
problem and no note.

[examples/coffee/coffee.json](../examples/coffee/coffee.json) is a longer file of this kind,
with a condition and a retry.

The weakness of this way is that nothing ties the file to the code. When the code changes
and the file does not, the outline is wrong and nothing says so.

## Way 2: have the program print the JSON

Keep the moves as a table in the program's own code, and add a flag that prints the table
as JSON. `shape` runs the command each time it opens, so the outline is never older than
the code.

In Python, copy [python/shapetable.py](../python/shapetable.py) into your project. It is
one file and needs nothing else. Save this as `orders.py` beside it:

```python
import sys

from shapetable import Machine, T


def can_try_again(order):
    """Fewer than three tries have been made, so the card is tried again."""
    return order["tries"] < 3


MACHINE = Machine(
    "orders.fulfil", initial="new", goal="shipped",
    about="Takes one order from the basket to the door.",
    attention=["declined", "failed"],
    transitions=[
        T("submit",    "new",    "submitted", "paying"),
        T("paid",      "paying", "paid",      "shipped",  output="print_label"),
        T("declined",  "paying", "declined",  "declined", output="email_customer"),
        T("try_again", "paying", "no_answer", "paying",   guard=can_try_again),
        T("gave_up",   "paying", "no_answer", "failed"),
    ])

if "--shape" in sys.argv:
    MACHINE.print_json()
    sys.exit(0)
```

Each `T` line is one move. It gives the move's name, the state it starts in, the event,
and the state it leads to.

- **guard** is a function that answers yes or no. `shape` prints the first paragraph of its
  docstring beside the condition.
- **output** names what the move does on the way. The outline shows it after the target,
  and the JSON lists it under the move's `actions`.
- **Mistakes are refused at once.** `Machine` raises `ValueError` when the program starts if
  two moves share a name, or if the start state, the goal or a state in `attention` is in no move.
- **`MACHINE.step(state, event, order)`** gives the move to take. It raises `NoTransition` when
  the state has no move for that event, or when every condition says no.

To look at the table once, before you write anything else, pipe it into `shape`:

```bash
python3 orders.py --shape | shape --file -
```

The `-` tells `shape` to read the JSON from the pipe. It prints the outline and exits.

In another language, build the same JSON from a table of your own.
[examples/download/download.js](../examples/download/download.js) does it in JavaScript in
about fifteen lines, with no library. [FORMAT.md](FORMAT.md) describes every key.

A program can have more than one table. It then prints them together as
`{"machines": [...]}`, and in Python `shapetable.dump([FIRST, SECOND])` does that.

## Way 3: make the table the program

Way 2 still allows the code to do one thing while the table says another. The last step is
to make the program take every move by looking it up in the table. Add this to the end of
`orders.py`:

```python
def submit(order):
    return "submitted"


def charge(order):
    order["tries"] += 1
    return {"good": "paid", "refused": "declined", "slow": "no_answer"}[order["card"]]


WORK = {"new": submit, "paying": charge}


def fulfil(order):
    state = MACHINE.initial
    while state in WORK:
        event = WORK[state](order)                 # do the work of this state, and say what happened
        move = MACHINE.step(state, event, order)   # the table says where that leads
        print("    %s %s -> %s" % (state, event, move.target))
        state = move.target
    return state


if __name__ == "__main__":
    for card in ("good", "refused", "slow"):
        print("An order paid with a %s card:" % card)
        print("    it ends in %s" % fulfil({"card": card, "tries": 0}))
```

`WORK` maps each state that has work to do to the function that does it. Each function
returns an event, never a state. The loop stops at a state that is not in `WORK`, so the
ends need no entry.

State names may be keys of `WORK`, but the program never writes a state name as the place
to go next. Only the table says where a move leads. Now the JSON that `--shape` prints is
the program, not a description of it.

The loop prints each move it takes as a line of the form `state event -> target`. That
line is what a test can check. Save this test as `test_orders.py` beside `orders.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args):
    done = subprocess.run([sys.executable, "orders.py", *args], cwd=HERE,
                          capture_output=True, text=True, check=True)
    return done.stdout


def test_every_move_the_program_takes_is_in_its_table():
    table = json.loads(run("--shape"))
    allowed = {(state, event, branch["target"])
               for state, body in table["states"].items()
               for event, branches in body["on"].items()
               for branch in branches}
    taken = [tuple(line.replace("->", " ").split()) for line in run().splitlines() if "->" in line]
    assert taken, "the program printed no moves"
    assert set(taken) <= allowed
```

Run it with `python3 -m pytest test_orders.py`. It runs the program, reads every move the
program prints, and fails when one of them is not in the table that `--shape` prints.

[examples/orders/orders.py](../examples/orders/orders.py) is a longer program of this kind.
Its tests in [tests/test_examples.py](../tests/test_examples.py) also read the code. They
fail when the state is set from anywhere but the table.

### Two events, or one event and a condition

Each decision in the program becomes either separate events or one event with a condition.

- **Use two events when the work finds out the answer.** The bank says whether a card is
  refused, so `charge` returns `declined` or `paid`.
- **Use one event and a condition when the program already knows the answer.** The program
  counts its own tries, so `no_answer` has the condition `can_try_again`.

## Tell shape where your programs are

Put a file called `shape.json` at the top of your project. It is a list of sources, and a
source is either a file or a command. This one lists the two programs this page built:

```json
[
  {"command": ["python3", "orders.py", "--shape"]},
  {"file": "door.json"}
]
```

- Paths start from the folder that holds `shape.json`, and commands run in that folder.
- A command is a list of words. It is not passed through a shell.
- A first word that is a path, such as `tools/emit.sh`, starts from that folder too. A bare
  name such as `python3` is found on your PATH, even when the project holds a file of that name.
- A command has 60 seconds to print its JSON.
- `shape` finds the file from any folder inside the project, the way `git` finds its folder.
- A program in another language goes in the same list, such as
  `{"command": ["node", "download.js", "--shape"]}`.

`shape` runs the commands in `shape.json` every time it runs, `shape --check` included.
List only commands that print and do nothing else.

`shape` runs them only when the `shape.json` belongs to you and nobody else can change it.
Otherwise it lists each command as a source it could not read, and says why.
`shape --config PATH` runs them anyway, so read a `shape.json` you did not write before you
use it.

## Check it

```bash
shape --check
```

A problem is something `shape` cannot show, such as a branch with no target. A note is
advice about something you probably did not mean, such as a state nothing leads to. The
command exits with 1 when there is a problem or a source it could not read, so it can run in
your tests.

You are done when these four things are true:

1. `shape --check` reports no problem and no note, and its last line says the programs are fine.
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
4. Where one event can lead to two states, decide whether the work or the program knows the
   answer, as described above. A condition is a small function with one sentence of description.
5. Mark the states a person should look at, usually the failures.
6. Change the code so that it takes its moves from the table, one state at a time, and run
   the program's own tests after each change.

Start with one part of the program. A table of six states that is true is worth more than
a table of sixty that is a guess.
