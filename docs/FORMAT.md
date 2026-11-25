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
| `goal` | no | The state the program is meant to reach. |
| `defined_in` | no | The file the table is in. It is shown beside the name. |

`shape` ignores any other key, and `shape --check` notes it, because it is often a spelling mistake.

## A state

A state is an object with one key, `on`, which holds one entry for each event the state takes.
A state with no events is an end state. Write it as `{}`, `{"on": {}}` or `null`.

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
| `id` | no | A name for the move. It is useful in logs. |

A guard is an object:

| Key of a guard | Needed | What it is |
|---|---|---|
| `name` | yes | The name shown after "if". |
| `says` | no | One sentence that says what the condition means. It is listed under "Conditions". |
| `source` | no | Where the condition is written, as `path/file.py:line`. |

When a guard has a `source` in a Python file and no `says`, `shape` reads the first paragraph
of the docstring of the function on that line. It parses the file and does not run it. The
path starts from the folder that holds `shape.json`.

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
commands run there.

The registry is for a program whose JSON you cannot change. Each of its entries looks like
`{"id": "orders.fulfil", "about": "...", "attention": ["failed"], "path": "orders.py"}`. What
the description says itself always wins.

## What shape works out

Nothing below is in the JSON. `shape` works it out each time.

| What it shows | How it gets it |
|---|---|
| The order of the states | It follows the moves from the start state, nearest first. |
| An end state | A state with nothing under `on`. |
| Ways it goes wrong | Every move into a state listed in `attention` from another state. |
| Routes | Every way from the start to an end that visits no state twice. Counting stops at 2,000. |
| Goes back | Every move to the same state or to a state that comes earlier. |
| Never reached | Every state that no chain of moves from the start leads to. |
| "never tried" | A branch written after a branch that has no condition. |
| "otherwise no transition is declared" | An event whose branches all have conditions. |

## What is a problem and what is a note

`shape --check` reports a problem when it cannot show the description. These are the problems:

- The description is not an object, or it lacks `id`, `initial` or `states`.
- `initial` is not one of the states.
- A state is not an object, or its `on` is not an object.
- An event lists no branch, a branch has no `target`, or a guard has no `name`.
- `attention` is not a list of names, or `goal`, `about` or `defined_in` is not a string.

It reports a note when the description can be shown but probably says something you did
not mean. These are the notes:

- A branch leads to a state that has no entry under `states`.
- `attention` or `goal` names something that is not a state.
- A state is never reached, a branch is never tried, or an event has no branch for when no
  condition holds.
- Two branches have the same `id`.
- A condition has no sentence.
- There is no `about` or no `attention` list.
- There is a key that `shape` does not read.
