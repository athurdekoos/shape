# shape: see the shape of a program

`shape` shows a program as an outline you can read from top to bottom: the states it moves
through, every route from its start to an end, and every way it can go wrong. You do not
have to read the code to follow it.

It is for people who run programs that they did not write line by line, which now includes
anyone whose code is written by an AI. It draws nothing, runs none of your program's work
and changes nothing.

<!-- shape coffee --plain -->
```
coffee.machine
Makes one cup of coffee, from the press of the button to the full cup.
7 states, 8 transitions, 2 routes to an end, 2 ways it goes wrong
! marks a state that needs attention

▶ idle · start
      button_pressed → checking_water

  checking_water
      water_found → heating
      tank_empty → no_water !

  heating
      hot → brewing
      heater_error
        ├ if first_failure → heating · restart_heater
        └ otherwise → broken !

  no_water · needs attention
      tank_filled → checking_water

  brewing
      cup_full → served

  served · end · goal

  broken · end · needs attention

Ways it goes wrong (2)
    checking_water   tank_empty     → no_water
    heating          heater_error   → broken

Routes from start to an end (2)
  ends in served
    idle → checking_water → heating → brewing → served
  ends in broken, which needs attention
    idle → checking_water → heating → broken

Goes back (2)
    heating    heater_error if first_failure   → heating
    no_water   tank_filled                     → checking_water

Conditions (1)
    first_failure   The heater has failed once, so it is tried one more time.
```

That is the whole of a small coffee machine, and it is the real output of
`shape coffee --plain`. The `!` marks a state that needs a person's attention.

## Try it in one minute

You need Python 3.9 or later and nothing else.

```bash
git clone https://github.com/athurdekoos/shape
cd shape
bin/shape
```

A screen opens and stays open. It lists three example programs. Move with the arrow keys,
press Enter to open one, Esc to go back, `?` for help on reading the outline, and `q` to close.

To type `shape` from any folder, run `scripts/install.sh` once. It puts one link in
`~/.local/bin` and copies nothing.

## Show your own program

`shape` reads JSON. Your program keeps its moves in one table and prints that table as JSON.
There are three ways to get there, and each one is a step up from the one before.

| Way | What you do | What you can trust |
|---|---|---|
| 1. A file you write | Write the states and events in a JSON file by hand. | A first look. The file can drift from the code. |
| 2. A command that prints it | Keep the table in the program and add a flag that prints it as JSON. Any language works. | The outline is as fresh as the code, because it is made again each time. |
| 3. The table is the program | The program takes every move by looking it up in the table. | The outline is what the program does, because there is no second copy. |

Then list the program in a file called `shape.json` at the top of your project:

```json
[
  {"command": ["python3", "orders.py", "--shape"]},
  {"file": "docs/coffee.json"}
]
```

Type `shape` anywhere inside that project and your programs are on the screen. Type
`shape --check` and it tells you, in sentences, what is wrong with the JSON and what you
probably did not mean.

- [docs/PLUG-IN.md](docs/PLUG-IN.md) walks through all three ways with code.
- [docs/FORMAT.md](docs/FORMAT.md) is the format itself, and
  [schema/shape.schema.json](schema/shape.schema.json) is the same format for a tool.
- [examples/](examples/) has one program for each way: a JSON file written by hand, a Python
  program and a JavaScript program.
- [python/shapetable.py](python/shapetable.py) is one file a Python program can copy. It
  holds the table, runs the program through it and prints the JSON.

## Ask an AI to do it

If an AI writes your code, ask it to do the work. This is the short form of the prompt:

> Read docs/PLUG-IN.md and docs/FORMAT.md in the shape repository. Find the part of my
> program that moves through steps. Show me its states, its events and its conditions, and
> wait for my yes. Then keep those moves in one table that the program runs through, add a
> `--shape` flag that prints the table as JSON, list the program in `shape.json`, and run
> `shape --check` until it reports no problems.

[docs/PROMPTS.md](docs/PROMPTS.md) has the full prompt, a prompt for building a viewer of
your own from nothing, and a prompt for checking that the outline is real.

## Use it

| Command | What it does |
|---|---|
| `shape` | Opens the screen on the list of programs. |
| `shape orders` | Opens straight on one program. Part of its name is enough. |
| `shape orders --plain` | Prints the same text and exits. A pipe or an AI agent gets this without asking. |
| `shape orders --plain --all` | Prints every route, however many there are. |
| `shape --check` | Checks the JSON of every program and says what is wrong. |
| `shape --file one.json` | Reads one JSON file. No `shape.json` is needed. |
| `shape --config path/shape.json` | Uses that list of programs. `SHAPE_CONFIG` in the environment does the same. |

| Key | What it does |
|---|---|
| up, down (or `k`, `j`) | Moves in the list, and scrolls in an outline. |
| Enter | Opens the picked program. |
| space, `b` | Goes a page down, and a page up. |
| `g`, `G` | Goes to the top, and to the bottom. |
| `a` | Shows every route. Press it again to go back to the short lists. |
| Esc | Goes back to the list. |
| `?` | Explains how to read the outline. |
| `q` | Closes the screen. |

When no `shape.json` is found in the folder you are in, or in a folder above it, `shape` shows
its own examples and says so.

## How to read an outline

The states that lead somewhere come first, in the order the program reaches them. The end
states follow: the ones that are fine, then the ones that need attention.

Under the states there are up to five lists.

| List | What it holds |
|---|---|
| Ways it goes wrong | Every move into a state that needs attention, with the event and the condition that cause it. |
| Routes from start to an end | Every way from the start state to an end state that does not visit a state twice. |
| Goes back | Every move that returns to an earlier state, such as a retry. |
| Conditions | Each condition by name, with the sentence written beside it in the program. |
| Never reached | The states that nothing leads to from the start. The list appears only when there are some. |

The outline also flags two mistakes in a table. A branch that can never be tried, because an
earlier branch has no condition, is marked "never tried". An event whose branches all have
conditions ends with "otherwise no transition is declared".

## What it does not show

- It does not show a program, or a part of one, that has no table. `shape` reads no source
  code to work out what a program does.
- It does not show whether the program follows its table. Only the third way above makes that true, and
  [docs/PLUG-IN.md](docs/PLUG-IN.md) shows a test that keeps it true.
- It does not show an error that the program handles without changing state.
- It does not show steps inside a state, or tables inside tables. The format is flat.
- It does not show where a running program is right now.

## How it is built

| File | What it holds |
|---|---|
| `bin/shape` | The command. |
| `lib/shapeformat.py` | The format, read strictly: the shorthands and the problems. |
| `lib/shapeview.py` | The outline: the model, its lines, the list, the check and the command line. |
| `lib/screen.py` | The screen that stays open, and reading the sources. |
| `python/shapetable.py` | The one file a Python program copies. `shape` itself does not use it. |

It uses the Python standard library only. Run the tests with `python3 -m pytest -q`. One
test needs the `jsonschema` package and one needs Node.js; each is skipped when its tool is missing.

It is tested on Linux. It was written and used on macOS. It has not been tried on Windows,
where Python does not include the `curses` module that the screen uses.

## Where the idea came from

The idea is ThePrimeagen's. In the video "The Joy of coding is Gone | Prime Reacts", about
nine minutes in, he shows a screen in his editor that lists each part of his program as an
outline of states, and says that he can trust it because it is printed from the code that
runs. `shape` copies that idea. It uses none of his code.

The JSON follows the layout that [XState](https://github.com/statelyai/xstate) uses for
states and events. `shape` does not use XState, and it reads only a flat table, not
everything XState can describe.

## Status and licence

This is version 0.1. It was built in November 2026, and one person uses it on her own
programs. The format may still change, and [docs/FORMAT.md](docs/FORMAT.md) will say so when it does.

The licence is MIT; see [LICENSE](LICENSE). [CONTRIBUTING.md](CONTRIBUTING.md) says how to
propose a change.
