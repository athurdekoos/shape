# The format shape reads

One program is one JSON object. This page describes every key. The same format is in
[schema/shape.schema.json](../schema/shape.schema.json) as a JSON Schema, and in
[lib/shapeformat.py](../lib/shapeformat.py) as the code that reads it.

This is version 0.1 of the format. It may still change.

## A whole description

```json
{
  "id": "orders.fulfil",
  "about": "Takes one order from the basket to the door.",
  "defined_in": "orders/orders.py",
  "initial": "new",
  "goal": "shipped",
  "attention": ["declined", "failed"],
  "states": {
    "new": {
      "on": {
        "submitted": [{"id": "submit", "target": "paying"}]
      }
    },
    "paying": {
      "on": {
        "paid": [{"id": "paid", "target": "shipped", "actions": ["print_label"]}],
        "error": [
          {
            "id": "declined",
            "target": "declined",
            "guard": {
              "name": "is_declined",
              "source": "orders/orders.py:22",
              "says": "The bank refused the card."
            }
          },
          {"id": "pay_failed", "target": "failed"}
        ]
      }
    },
    "shipped": {"on": {}},
    "declined": {"on": {}},
    "failed": {"on": {}}
  }
}
```

## The keys of a description

| Key | Needed | What it is |
|---|---|---|
| `id` | yes | The name `shape` lists the program under. A dotted name such as `orders.fulfil` reads well. |
| `initial` | yes | The state the program starts in. It must be one of the states. |
| `states` | yes | An object with one entry for each state. |
| `about` | no | One sentence that says what the program is. It is shown in the list and at the top of the outline. |
| `attention` | no | A list of the states a person should look at, usually the failures. `shape` marks them with `!` and lists every move into one under "Ways it goes wrong". |
| `goal` | no | The state the program is meant to reach. The outline marks it with the word goal. |
| `defined_in` | no | The file the table is in. It is shown beside the name. |
| `$schema` | no | The address of a JSON Schema, for an editor that checks the file as you type. `shape` does not use it. |

`shape` ignores any other key, wherever it is: in the description, in a state, in a branch or
in a guard. `shape --check` notes each one, because it is often a spelling mistake.

A description may name at most 2,000 states, counting the targets of its branches, and it
may have at most 20,000 branches.

## A state

A state is an object with one key, `on`. It holds one entry for each event that can happen
in that state. A state with no events is an end state. Write it as `{}`, `{"on": {}}` or `null`.

The order of the states does not matter. `shape` shows them in the order the program
reaches them.

## An event and its branches

The value of an event is a list of branches. They are tried in the order they are written.
The first branch whose condition holds, or that has no condition, is taken.

| Key of a branch | Needed | What it is |
|---|---|---|
| `target` | yes | The state this branch leads to. |
| `guard` | no | The condition. Without one, the branch is always taken when it is reached. |
| `actions` | no | Names for what the move does, such as `["send_email"]`. They are shown after the target. |
| `id` | no | A name for the move, for your own logs. `shape` shows it nowhere, and `shape --check` notes an id that two branches share. |

A guard is an object:

| Key of a guard | Needed | What it is |
|---|---|---|
| `name` | yes | The name shown after "if". |
| `says` | no | One sentence that says what the condition means. It is listed under "Conditions". |
| `source` | no | Where the condition is written, as `path/file.py:line`. |

When a guard has a `source` in a Python file and no `says`, `shape` reads the first paragraph
of the docstring of the function that starts on that line. It parses the file and does not run it.

- The path starts from the folder that holds `shape.json`.
- With `--file PATH`, it starts from the folder that holds that file.
- With `--file -`, it starts from the folder `shape` was typed in.
- `shape` reads the file only when it is inside that folder, is a regular file and holds at
  most 1 MB.

## Shorthands

A file written by hand can be shorter. Each line below means the same as the line under it.

```json
"push": "open"
"push": [{"target": "open"}]
```

```json
"push": {"target": "open", "actions": "creak"}
"push": [{"target": "open", "actions": ["creak"]}]
```

```json
"jam": [{"target": "stuck", "guard": "is_rusty"}, "closed"]
"jam": [{"target": "stuck", "guard": {"name": "is_rusty"}}, {"target": "closed"}]
```

## More than one program

A source may give one description, a list of descriptions, or an object with the key
`machines` that holds a list:

```json
{"machines": [{"id": "orders.fulfil", "...": "..."}, {"id": "orders.refund", "...": "..."}]}
```

Two descriptions may not have the same `id`.

## shape.json

`shape.json` is a list of sources. `shape` uses the one in the folder it is typed in, or in
the nearest folder above it.

| Key of a source | What it is |
|---|---|
| `file` | The path of a JSON file. |
| `command` | A list of words to run. The command prints the JSON and exits with 0. |
| `registry` | Optional. The path of a JSON list that adds `about`, `attention` and `path` to descriptions by `id`. |

A source has `file` or `command`. Paths start from the folder that holds `shape.json`, and
commands run there. A key that `shape` does not read is noted by `shape --check`.

`shape` runs the commands every time it runs, `shape --check` included. It runs them only
when the `shape.json` belongs to you and nobody else can change it. One named with
`--config` or `SHAPE_CONFIG` is always run.

The registry is for a program whose JSON you cannot change. Each of its entries looks like
`{"id": "orders.fulfil", "about": "...", "attention": ["failed"], "path": "orders.py"}`.
Its `path` fills in `defined_in`. A value the description gives itself wins, unless it is
an empty string.

`shape` lists a source it could not read under "Could not read", with a sentence that says
why. These are the reasons:

- The file is missing, is not UTF-8 text or is not JSON.
- A key is written twice in one object, which JSON would quietly read as the last one.
- The JSON is nested too deeply to read, or a path holds a NUL character.
- The command is not a list of words, did not finish in 60 seconds, exited with a number
  other than 0, or printed text that is not UTF-8.
- The command was not run, because the `shape.json` is not yours or others can change it.

Two more cases appear under "Could not read" in the list of programs: an entry that is not a
description, and a second description with an `id` already used. `shape --check` reports
those two as problems.

## What shape works out

Nothing below is in the JSON. `shape` works it out each time.

| What it shows | How it gets it |
|---|---|
| The order of the states | It follows the moves from the start state, nearest first. |
| An end state | A state with nothing under `on`. |
| Ways it goes wrong | Every move into a state listed in `attention` from another state. |
| Routes | Every way from the start to an end that visits no state twice. Counting stops at 2,000 routes, or after 200,000 steps. |
| Goes back | Every move to the same state, or back to an earlier state from which this one can be reached again. |
| Never reached | Every state that no chain of moves from the start leads to. |
| "never tried" | A branch written after a branch that has no condition. |
| "otherwise no transition is declared" | An event whose branches all have conditions. |

A branch marked "never tried" leads nowhere, because the program never takes it. It is left
out of the routes, the ways it goes wrong, the moves that go back and the states that are reached.

## What is a problem and what is a note

`shape --check` reports a problem when it cannot show the description. These are the problems:

- The description is not an object.
- Its `id`, `initial` or `states` is missing, empty or of the wrong kind.
- `initial` is not one of the states.
- It names more than 2,000 states or has more than 20,000 branches.
- A state is not an object, or its `on` is not an object.
- An event lists no branch.
- A branch is not a name or an object, or it has no `target`.
- A branch's `id` is not a string, or it is an empty string.
- A branch's `actions` is not a name or a list of names.
- A guard is not a name or an object, it has no `name`, or its `says` or `source` is not a string.
- `attention` is not a list of names.
- `goal` is not a name, or `about` or `defined_in` is not a string.
- Another description, from this source or another, has the same `id`.

It reports a note when the description can be shown but probably says something you did
not mean. These are the notes:

- A branch leads to a state that has no entry under `states`.
- `attention` or `goal` names something that is not a state.
- A state is never reached, a branch is never tried, or an event has no branch for when no
  condition holds.
- Two branches have the same `id`.
- A condition has no sentence.
- There is no `about` or no `attention` list.
- There is a key that `shape` does not read, in the description or in its source in `shape.json`.
