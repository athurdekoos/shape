# What to ask an AI

These are prompts to paste into a coding assistant. The first one adds your program to
`shape`. The second one builds a viewer of your own from nothing, which is how `shape` began.
The third one checks that the result is real.

Change the words in capitals before you paste.

## 1. Show my program in shape

> I want to see my program in shape, the outline viewer at https://github.com/athurdekoos/shape.
> Clone it beside this project. Read its docs/PLUG-IN.md and docs/FORMAT.md before you
> change anything.
>
> 1. Find the part of this project that moves through steps: THE SYNC JOB. List its states,
>    the events that can happen in each state, and the conditions that choose between two
>    outcomes. Show me that list in plain words and wait for my yes.
> 2. Write those moves as one table in the program's own language. In Python, copy
>    python/shapetable.py from the shape repository into this project and use it.
> 3. Change the program so that it takes every move by looking it up in the table. The name
>    of the next state must appear nowhere but the table. Do not write a second description
>    beside the code. Run this project's tests after each change.
> 4. Add a `--shape` flag that prints the table as JSON in shape's format and does nothing else.
> 5. Give the table one sentence that says what the program is, list the states a person
>    should look at under `attention`, and give every condition one sentence.
> 6. Add the command to a `shape.json` at the top of this project.
> 7. Run `shape --check` and fix everything it reports, the notes as well as the problems.
> 8. Add a test that runs the program and fails when it takes a move that is not in the table.
>
> When you are done, show me the output of `shape NAME --plain` and tell me which parts of
> the program are not in the table.

For a first look that changes no code, ask for less:

> Read docs/FORMAT.md in the shape repository. Read THE SYNC JOB in this project and write
> its states, events and conditions as one JSON file in that format. Change no code. Run
> `shape --check --file THAT_FILE` and fix what it reports. Tell me where you were unsure
> what the code does.

## 2. Build a viewer of your own from nothing

The first version of `shape` came from three short requests in one evening, on top of
tables that the programs already had. With nothing in place, ask for three things in this order.

**The table.**

> Find the part of this program that moves through steps. Rewrite it so that its moves are
> one table in the code: in this state, on this event, go to that state, with a named
> condition where one event has two outcomes. The program must take every move by looking it
> up in that table. Write the tests first, and keep the existing tests passing.

**The JSON.**

> Add a function that prints the table as JSON: the states, the events each state takes, and
> for each event its branches in order, each with its target and the name of its condition.
> Add a flag that prints it and exits. Nobody should ever type this JSON by hand.

**The viewer.**

> Build a command with a one-word name that reads that JSON and shows the program as a text
> outline. For each state it shows the events and where each one leads. Under the states it
> lists every way into a failure state, every route from the start to an end, every move
> that goes back, and what each condition means. It draws no diagram. It opens a screen that
> stays open until I press q, with a list of programs first, and it prints plain text when
> its output is a pipe. Use the standard library only. Write the tests first.

The idea for that third request is a screen that ThePrimeagen shows in the video "The Joy
of coding is Gone | Prime Reacts", about nine minutes in.

## 3. Check that it is real

An outline is only worth reading when the program follows it. Ask for evidence.

> Show me that the outline is what the program does, without asking me to trust you.
>
> 1. Find every place where the program changes state, and show that each one takes its
>    move from the table.
> 2. Copy the project to a temporary folder. Change one move in the table there, and show
>    that both the outline and the program's behaviour change.
> 3. Run the program on real input, record the moves it takes, and show that every one is in
>    the table.
> 4. Break the viewer on purpose in five ways, one at a time, and tell me which of its tests
>    fail for each. Say plainly which breakages no test caught.
>
> Report what failed as well as what passed.
