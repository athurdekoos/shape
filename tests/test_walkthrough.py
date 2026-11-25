"""Tests for docs/walkthrough: the backup script before it had a table and after. The six tests the
script came with pass for both, so giving it a table changed nothing it does. The rest check that
the program with the table takes only moves that are in the table."""
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WALK = str(REPO / "docs" / "walkthrough")
SHAPE = REPO / "bin" / "shape"
MOVE = re.compile(r"^\s+(\S+)\s+(\S+)\s+->\s+(\S+)\s*$")


def load(name):
    spec = importlib.util.spec_from_file_location("walkthrough_" + name, os.path.join(WALK, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULES = {"before": load("before"), "after": load("after")}
after = MODULES["after"]


@pytest.fixture(params=["before", "after"])
def backup(request):
    """The program in each of its two forms."""
    return MODULES[request.param]


# ---- what the script did before it had a table, and still does ----

def make(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("alpha")
    (src / "b.txt").write_text("beta")
    return str(src), str(tmp_path / "dest")


def test_a_backup_copies_the_files(backup, tmp_path):
    src, dest = make(tmp_path)
    assert backup.run(src, dest, log=lambda m: None) == "done"
    assert open(os.path.join(dest, "files", "a.txt")).read() == "alpha"
    assert not os.path.exists(os.path.join(dest, backup.LOCK))


def test_a_full_disk_stops_it_before_anything_is_written(backup, tmp_path):
    src, dest = make(tmp_path)
    assert backup.run(src, dest, free_bytes=1, log=lambda m: None) == "disk_full"
    assert not os.path.exists(dest)


def test_a_second_run_is_skipped_while_the_lock_is_held(backup, tmp_path):
    src, dest = make(tmp_path)
    os.makedirs(dest)
    open(os.path.join(dest, backup.LOCK), "w").close()
    assert backup.run(src, dest, log=lambda m: None) == "skipped"


def test_a_copy_that_fails_is_tried_three_times(backup, tmp_path):
    src, dest = make(tmp_path)
    calls = []

    def broken(*a, **k):
        calls.append(1)
        raise OSError("disk unplugged")

    assert backup.run(src, dest, copy=broken, log=lambda m: None) == "copy_failed"
    assert len(calls) == 3


def test_a_copy_that_fails_once_then_works_is_done(backup, tmp_path):
    import shutil
    src, dest = make(tmp_path)
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("hiccup")
        return shutil.copytree(*a, **k)

    assert backup.run(src, dest, copy=flaky, log=lambda m: None) == "done"


def test_a_copy_that_differs_is_reported_as_corrupt(backup, tmp_path):
    src, dest = make(tmp_path)

    def lossy(s, d, **k):
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "a.txt"), "w").write("alpha")

    assert backup.run(src, dest, copy=lossy, log=lambda m: None) == "corrupt"


# ---- the program takes only the moves in its table ----

def table():
    """Every move in the table, as (state, event, next state), read from what --shape prints."""
    out = subprocess.run([sys.executable, "after.py", "--shape"], cwd=WALK,
                         capture_output=True, text=True, check=True).stdout
    doc = json.loads(out)
    return {(state, event, branch["target"]) for state, body in doc["states"].items()
            for event, branches in body["on"].items() for branch in branches}


def test_every_move_the_job_takes_is_in_its_table(tmp_path):
    import shutil
    taken = []

    def record(state, event, target):
        taken.append((state, event, target))

    def broken(*a, **k):
        raise OSError("disk unplugged")

    def flaky(*a, **k):
        flaky.calls += 1
        if flaky.calls == 1:
            raise OSError("hiccup")
        return shutil.copytree(*a, **k)
    flaky.calls = 0

    def lossy(s, d, **k):
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "a.txt"), "w").write("alpha")

    def held(src, dest):
        os.makedirs(dest)
        open(os.path.join(dest, after.LOCK), "w").close()

    cases = {"plain": {}, "full": {"free_bytes": 1}, "held": {}, "broken": {"copy": broken},
             "flaky": {"copy": flaky}, "lossy": {"copy": lossy}}
    ends = set()
    for name, options in cases.items():
        (tmp_path / name).mkdir()
        src, dest = make(tmp_path / name)
        if name == "held":
            held(src, dest)
        ends.add(after.run(src, dest, log=lambda m: None, trace=record, **options))

    moves = table()
    assert set(taken) <= moves, "moves not in the table: %s" % sorted(set(taken) - moves)
    assert set(taken) == moves, "moves in the table no case took: %s" % sorted(moves - set(taken))
    assert len(ends) == 5


def test_the_command_takes_only_moves_that_are_in_its_table(tmp_path):
    src, dest = make(tmp_path)
    r = subprocess.run([sys.executable, os.path.join(WALK, "after.py"), src, dest, "--trace"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    taken = [m.groups() for m in map(MOVE.match, r.stdout.splitlines()) if m]
    assert len(taken) == 4
    assert set(taken) <= table()


def test_the_state_is_only_ever_set_from_the_table():
    """In after.py the state is set to MACHINE.initial at the start, and after that only to the
    target of the move that MACHINE.step gave."""
    tree = ast.parse(open(os.path.join(WALK, "after.py")).read())
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Name) and n.id == "state" and isinstance(n.ctx, ast.Store)]
    set_to = [ast.unparse(n.value) for n in ast.walk(tree)
              if isinstance(n, ast.Assign) and len(n.targets) == 1
              and getattr(n.targets[0], "id", "") == "state"]
    assert len(stores) == 2 and sorted(set_to) == ["MACHINE.initial", "move.target"]
    moves = [ast.unparse(n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "move"]
    assert moves == ["MACHINE.step(state, event, job)"]


def test_no_state_is_named_outside_the_table():
    """A state name may be written only in MACHINE and as a key of WORK, so the program cannot pick
    its next state by itself."""
    tree = ast.parse(open(os.path.join(WALK, "after.py")).read())
    names = {s for s, _e, _t in table()} | {t for _s, _e, t in table()}
    named = {n.targets[0].id: n.value for n in ast.walk(tree)
             if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("MACHINE", "WORK")}
    allowed = {id(n) for n in ast.walk(named["MACHINE"])} | {id(k) for k in named["WORK"].keys}
    stray = [(n.lineno, n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and n.value in names and id(n) not in allowed]
    assert stray == []


# ---- the page about it ----

def test_the_walkthrough_is_fine_by_check_and_its_page_shows_the_real_outline():
    r = subprocess.run([sys.executable, str(SHAPE), "--check"], capture_output=True, text=True, cwd=WALK)
    assert r.returncode == 0 and "1 program checked: it is fine." in r.stdout, r.stdout + r.stderr
    page = (REPO / "docs" / "walkthrough" / "README.md").read_text()
    block = page.split("<!-- shape backup --plain -->", 1)[1].split("```", 2)[1].split("\n", 1)[1]
    real = subprocess.run([sys.executable, str(SHAPE), "backup", "--plain"], capture_output=True, text=True, cwd=WALK)
    assert block.strip() == real.stdout.strip()


def test_the_page_quotes_lines_that_are_in_the_two_files():
    page = (REPO / "docs" / "walkthrough" / "README.md").read_text()
    fence = "```"
    blocks = [p.split("\n", 1)[1] for n, p in enumerate(page.split(fence)) if n % 2 and p.startswith("python\n")]
    assert len(blocks) == 2
    for block, name in zip(blocks, ("before.py", "after.py")):
        source = (REPO / "docs" / "walkthrough" / name).read_text().splitlines()
        for line in block.splitlines():
            if line.strip() and line.strip() != "...":
                assert line in source, "%s has no line %r" % (name, line)
