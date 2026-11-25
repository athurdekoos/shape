#!/usr/bin/env python3
"""backup: copy a folder to a backup disk, once. This is the program BEFORE it had a table.

    python3 before.py SOURCE DEST

The steps: check that the disk has room, take a lock so two runs cannot overlap, copy the
files, then compare checksums. A copy that fails is tried up to three times.

Every step and every ending is here, but you have to read the whole function to find them.
after.py is the same program with its steps moved into a table.
"""
import hashlib
import os
import shutil
import sys

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


def run(source, dest, free_bytes=None, copy=shutil.copytree, log=print):
    """Back up source into dest. Returns "done", "skipped", "disk_full", "copy_failed" or "corrupt"."""
    free = shutil.disk_usage(os.path.dirname(os.path.abspath(dest)) or ".").free if free_bytes is None else free_bytes
    if size_of(source) > free:
        log("not enough room on the backup disk")
        return "disk_full"
    os.makedirs(dest, exist_ok=True)
    lock = os.path.join(dest, LOCK)
    if os.path.exists(lock):
        log("another backup is running")
        return "skipped"
    open(lock, "w").close()
    try:
        tries = 0
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
    finally:
        os.remove(lock)


if __name__ == "__main__":
    result = run(sys.argv[1], sys.argv[2])
    sys.exit(0 if result in ("done", "skipped") else 1)
