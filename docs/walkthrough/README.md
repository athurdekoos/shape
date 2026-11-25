# One program, before and after

This folder shows what "giving a program a table" means on one small program. `before.py`
is a backup script as it was first written. `after.py` is the same script after its steps
were moved into a table that `shape` can show.

An AI made `after.py` on 25 November 2026. It was given `before.py`, its six tests, this
repository, and prompt 1 of [../PROMPTS.md](../PROMPTS.md), and nothing else. It took
about five minutes. A few lines were changed by hand afterwards: the file's name and the
docstring that gives it, the two lines that find `shapetable.py` in this repository, and the
removal of a class that nothing used.

## Before: the steps are inside one function

```python
def run(source, dest, free_bytes=None, copy=shutil.copytree, log=print):
...
    if size_of(source) > free:
        log("not enough room on the backup disk")
        return "disk_full"
...
        while True:
            tries += 1
            try:
                copy(source, os.path.join(dest, "files"), dirs_exist_ok=True)
                break
            except OSError as exc:
                log("copy failed (%s), try %d" % (exc, tries))
                if tries >= 3:
                    return "copy_failed"
        if checksum(source) != checksum(os.path.join(dest, "files")):
            log("the copy does not match the source")
            return "corrupt"
        log("backup complete")
        return "done"
```

The script works, and its tests pass. To learn how it can end, you have to read every
`if`, every `return` and the loop. Nothing lists the five endings in one place.

## Step 1: say what the states are

Before it changed any code, the AI listed what it found, in plain words:

| State | What can happen there | Where that leads |
|---|---|---|
| checking_room, the start | room_found, or no_room | locking, or disk_full |
| locking | locked, or lock_held | copying, or skipped |
| copying | copied, or copy_error | verifying; after an error, copying again while fewer than three tries were made, and copy_failed after that |
| verifying | matched, or mismatched | done, or corrupt |

The five endings are done, skipped, disk_full, copy_failed and corrupt. The last three
need a person's attention. This list is the place to catch a wrong reading of the program,
which is why the prompt says to wait for a yes.

## After: one table, and a loop that follows it

```python
MACHINE = Machine(
...
    transitions=[
        T("room_found", "checking_room", "room_found", "locking"),
        T("no_room",    "checking_room", "no_room",    "disk_full"),
        T("locked",     "locking",       "locked",     "copying"),
        T("lock_held",  "locking",       "lock_held",  "skipped"),
        T("copied",     "copying",       "copied",     "verifying"),
        T("try_again",  "copying",       "copy_error", "copying",   guard=can_try_again),
        T("give_up",    "copying",       "copy_error", "copy_failed"),
        T("matched",    "verifying",     "matched",    "done"),
        T("mismatched", "verifying",     "mismatched", "corrupt"),
    ])
...
        while state in WORK:
            event = WORK[state](job)
            move = MACHINE.step(state, event, job)
            before = state
            state = move.target
```

Each `T` line is one move: its name, the state it starts in, the event, and the state it
leads to. The work of each state moved into its own small function, which does the work and
returns the event that happened. The loop asks the table where that event leads. The name of
the next state is written nowhere but the table.

The six tests the script came with pass for both files, so the change altered nothing the
script does.

## What shape shows

<!-- shape backup --plain -->
```
backup.job   after.py
Copies one folder to a backup disk once: it checks for room, takes a lock, copies the files with up to three tries and compares checksums.
9 states, 9 transitions, 5 routes to an end, 3 ways it goes wrong
! marks a state that needs attention

▶ checking_room · start
      room_found → locking
      no_room → disk_full !

  locking
      locked → copying
      lock_held → skipped

  copying
      copied → verifying
      copy_error
        ├ if can_try_again → copying
        └ otherwise → copy_failed !

  verifying
      matched → done
      mismatched → corrupt !

  skipped · end

  done · end · goal

  disk_full · end · needs attention

  copy_failed · end · needs attention

  corrupt · end · needs attention

Ways it goes wrong (3)
    checking_room   no_room      → disk_full
    copying         copy_error   → copy_failed
    verifying       mismatched   → corrupt

Routes from start to an end (5)
  ends in skipped
    checking_room → locking → skipped
  ends in done
    checking_room → locking → copying → verifying → done
  ends in disk_full, which needs attention
    checking_room → disk_full
  ends in copy_failed, which needs attention
    checking_room → locking → copying → copy_failed
  ends in corrupt, which needs attention
    checking_room → locking → copying → verifying → corrupt

Goes back (1)
    copying   copy_error if can_try_again   → copying

Conditions (1)
    can_try_again   The copy has failed fewer than three times, so it is tried again.
                    after.py:46
```

## What is not in the table

The AI was asked to say this, and it is the honest limit of the method.

- The work inside each state is not in the table: measuring the disk, the lock file, the copy
  and the checksums.
- Three of the four decisions are made inside the work and appear only as event names. Only
  the retry is a condition with a sentence.
- Releasing the lock, the log messages and the command line are not in the table.
- An error the script does not handle, such as a missing source folder, has no state.

## Try it

```bash
cd docs/walkthrough
python3 after.py --shape          # the table as JSON
../../bin/shape                   # the outline, on the screen
../../bin/shape --check           # is the JSON fine?
```
