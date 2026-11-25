#!/usr/bin/env python3
"""backup: copy a folder to a backup disk, once. This is the program AFTER it was given a table.

    python3 after.py SOURCE DEST            back up SOURCE into DEST
    python3 after.py SOURCE DEST --trace    the same, and print each move it takes
    python3 after.py --shape                print the table of moves as JSON, which shape reads

The steps: check that the disk has room, take a lock so two runs cannot overlap, copy the
files, then compare checksums. A copy that fails is tried up to three times.

The moves from step to step are the table MACHINE. Each function in WORK does the work of one
state and says what happened, and MACHINE.step looks up where that leads. The exit code is 1
when the job ends in a state listed under attention, and 0 otherwise.
"""
import hashlib
import os
import shutil
import sys

# In your own project, copy python/shapetable.py beside your code and drop these two lines.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python"))

from shapetable import Machine, T  # noqa: E402

LOCK = ".backup.lock"


def size_of(folder):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _s, fs in os.walk(folder) for f in fs)


def checksum(folder):
    h = hashlib.sha256()
    for d, _s, fs in sorted(os.walk(folder)):
        for f in sorted(fs):
            if f == LOCK:
                continue
            h.update(os.path.relpath(os.path.join(d, f), folder).encode())
            with open(os.path.join(d, f), "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


# ---- the condition: its docstring is what shape prints beside it ----

def can_try_again(job):
    """The copy has failed fewer than three times, so it is tried again."""
    return job.tries < 3


# ---- the table: every move the backup job can take ----

MACHINE = Machine(
    "backup.job", initial="checking_room", goal="done",
    about="Copies one folder to a backup disk once: it checks for room, takes a lock, "
          "copies the files with up to three tries and compares checksums.",
    attention=["disk_full", "copy_failed", "corrupt"],
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


# ---- the work of each state: do it, then say what happened ----

class Job:
    """What one run knows: its folders, its tools, whether it holds the lock and how many tries it made."""

    def __init__(self, source, dest, free_bytes, copy, log):
        self.source, self.dest, self.free_bytes, self.copy, self.log = source, dest, free_bytes, copy, log
        self.lock = os.path.join(dest, LOCK)
        self.locked = False
        self.tries = 0


def check_room(job):
    free = job.free_bytes
    if free is None:
        free = shutil.disk_usage(os.path.dirname(os.path.abspath(job.dest)) or ".").free
    if size_of(job.source) > free:
        job.log("not enough room on the backup disk")
        return "no_room"
    return "room_found"


def take_lock(job):
    os.makedirs(job.dest, exist_ok=True)
    if os.path.exists(job.lock):
        job.log("another backup is running")
        return "lock_held"
    open(job.lock, "w").close()
    job.locked = True
    return "locked"


def copy_files(job):
    job.tries += 1
    try:
        job.copy(job.source, os.path.join(job.dest, "files"), dirs_exist_ok=True)
    except OSError as exc:
        job.log("copy failed (%s), try %d" % (exc, job.tries))
        return "copy_error"
    return "copied"


def compare(job):
    if checksum(job.source) != checksum(os.path.join(job.dest, "files")):
        job.log("the copy does not match the source")
        return "mismatched"
    job.log("backup complete")
    return "matched"


WORK = {"checking_room": check_room, "locking": take_lock, "copying": copy_files, "verifying": compare}


def run(source, dest, free_bytes=None, copy=shutil.copytree, log=print, trace=None):
    """Back up source into dest and return the end state that the table led to.

    trace, when given, is called with (state, event, next state) for each move taken."""
    job = Job(source, dest, free_bytes, copy, log)
    state = MACHINE.initial
    try:
        while state in WORK:
            event = WORK[state](job)
            move = MACHINE.step(state, event, job)
            before = state
            state = move.target
            if trace is not None:
                trace(before, event, state)
    finally:
        if job.locked:
            os.remove(job.lock)
    return state


def main(argv):
    if "--shape" in argv:
        MACHINE.print_json()
        return 0
    trace = None
    if "--trace" in argv:
        argv = [a for a in argv if a != "--trace"]

        def trace(state, event, target):
            print("    %-14s %-11s -> %s" % (state, event, target))
    end = run(argv[0], argv[1], trace=trace)
    return 1 if end in MACHINE.attention else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
