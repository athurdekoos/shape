"""Tests for the shape command: where it finds the programs, what it prints, and what it
says when something is wrong."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from terminal import Terminal

REPO = Path(__file__).resolve().parents[1]
SHAPE = REPO / "bin" / "shape"

DOOR = {"id": "demo.door", "initial": "closed", "about": "A door that opens or sticks.", "attention": ["stuck"],
        "states": {"closed": {"on": {"push": "open", "jam": "stuck"}}, "open": {}, "stuck": {}}}
LAMP = {"id": "demo.lamp", "initial": "off", "about": "A lamp.", "attention": [],
        "states": {"off": {"on": {"press": "on"}}, "on": {"on": {"press": "off"}}}}


def run(*args, cwd=None, exe=None, env=None, stdin=None):
    full = dict(os.environ)
    full.pop("SHAPE_CONFIG", None)
    full.update(env or {})
    return subprocess.run([sys.executable, str(exe or SHAPE), *args], capture_output=True, text=True, cwd=cwd, env=full,
                          input=stdin)


@pytest.fixture
def home(tmp_path):
    """A folder of someone's own with a shape.json that lists two programs."""
    (tmp_path / "door.json").write_text(json.dumps(DOOR))
    (tmp_path / "lamp.py").write_text("import json\nprint(json.dumps(%r))\n" % LAMP)
    (tmp_path / "shape.json").write_text(json.dumps([{"file": "door.json"}, {"command": [sys.executable, "lamp.py"]}]))
    return tmp_path


# ---- where the programs come from ----

def test_it_lists_the_programs_named_by_the_shape_json_in_this_folder(home):
    r = run(cwd=home)
    assert r.returncode == 0, r.stderr
    assert "demo.door" in r.stdout and "demo.lamp" in r.stdout and "A door that opens or sticks." in r.stdout
    assert "examples" not in r.stdout


def test_it_looks_in_the_folders_above(home):
    deep = home / "src" / "deep"
    deep.mkdir(parents=True)
    r = run("door", cwd=deep)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("demo.door")


def test_config_names_another_file_and_so_does_the_environment(home, tmp_path_factory):
    other = tmp_path_factory.mktemp("elsewhere")
    assert "demo.door" in run("--config", str(home / "shape.json"), cwd=other).stdout
    assert "demo.door" in run(cwd=other, env={"SHAPE_CONFIG": str(home / "shape.json")}).stdout
    r = run("--config", str(other / "missing.json"), cwd=other)
    assert r.returncode == 1 and "missing.json" in r.stderr


def test_file_reads_one_json_file_without_any_shape_json(tmp_path):
    (tmp_path / "door.json").write_text(json.dumps(DOOR))
    r = run("--file", "door.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "demo.door" in r.stdout and "examples" not in r.stdout
    assert run("door", "--file", "door.json", cwd=tmp_path).stdout.startswith("demo.door")


def test_a_file_with_one_program_opens_on_that_program(tmp_path):
    (tmp_path / "door.json").write_text(json.dumps(DOOR))
    r = run("--file", "door.json", cwd=tmp_path)
    assert r.stdout.startswith("demo.door") and "▶ closed · start" in r.stdout


def test_a_file_with_several_programs_lists_them_and_says_how_to_open_one(tmp_path):
    (tmp_path / "two.json").write_text(json.dumps({"machines": [DOOR, LAMP]}))
    r = run("--file", "two.json", cwd=tmp_path)
    assert "PROGRAM" in r.stdout and "demo.door" in r.stdout and "demo.lamp" in r.stdout
    assert "shape NAME --file two.json" in r.stdout


def test_a_dash_reads_the_json_from_standard_input(tmp_path):
    r = run("--file", "-", cwd=tmp_path, stdin=json.dumps(DOOR))
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("demo.door")
    assert "ok" in run("--check", "--file", "-", cwd=tmp_path, stdin=json.dumps(DOOR)).stdout
    bad = run("--file", "-", cwd=tmp_path, stdin="{not json")
    assert bad.returncode == 1 and "standard input" in bad.stderr and "Traceback" not in bad.stderr


def test_with_no_shape_json_it_shows_its_own_examples_and_says_so(tmp_path):
    r = run(cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "coffee.machine" in r.stdout and "orders.fulfil" in r.stdout
    assert "These are the examples that come with shape" in r.stdout and "PLUG-IN.md" in r.stdout


def test_it_works_through_a_link_from_any_folder(tmp_path):
    link = tmp_path / "bin" / "shape"
    link.parent.mkdir()
    os.symlink(SHAPE, link)
    r = run("coffee", cwd=str(tmp_path), exe=link)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("coffee.machine")


# ---- names ----

def test_part_of_a_name_is_enough_and_an_ambiguous_one_lists_the_candidates(home):
    assert run("lamp", cwd=home).stdout.startswith("demo.lamp")
    r = run("demo", cwd=home)
    assert r.returncode == 2 and "demo.door" in r.stderr and "demo.lamp" in r.stderr


def test_an_unknown_name_lists_what_exists(home):
    r = run("nope", cwd=home)
    assert r.returncode == 2 and "nothing is called" in r.stderr and "demo.door" in r.stderr


def test_an_unknown_name_says_when_the_list_is_the_examples(tmp_path):
    r = run("door", cwd=tmp_path)
    assert r.returncode == 2 and "coffee.machine" in r.stderr
    assert "examples that come with shape" in r.stderr and "--file" in r.stderr


def test_piped_output_is_plain(home):
    assert "\x1b[" not in run("door", cwd=home).stdout


def test_version():
    r = run("--version")
    assert r.returncode == 0 and r.stdout.startswith("shape ")


# ---- when something is wrong ----

def test_one_source_that_fails_does_not_hide_the_others(home):
    (home / "shape.json").write_text(json.dumps([{"file": "door.json"}, {"command": ["no-such-command-xyz", "--shape"]},
                                                 {"file": "missing.json"}]))
    r = run(cwd=home)
    assert r.returncode == 0, r.stderr
    assert "demo.door" in r.stdout
    assert "Could not read" in r.stdout and "no-such-command-xyz" in r.stdout and "missing.json" in r.stdout


def test_a_program_whose_json_is_wrong_is_named_with_its_problems(home):
    broken = dict(DOOR, id="demo.broken", states={"closed": {"on": {"push": {"guard": "g"}}}})
    (home / "broken.json").write_text(json.dumps(broken))
    (home / "shape.json").write_text(json.dumps([{"file": "door.json"}, {"file": "broken.json"}]))
    listing = run(cwd=home)
    assert listing.returncode == 0 and "demo.door" in listing.stdout
    assert "demo.broken" in listing.stdout and "shape --check" in listing.stdout
    one = run("broken", cwd=home)
    assert one.returncode == 1
    assert 'state "closed", event "push"' in one.stderr and "Traceback" not in one.stderr


def test_a_shape_json_that_is_wrong_is_reported(tmp_path):
    (tmp_path / "shape.json").write_text("{not json")
    r = run(cwd=tmp_path)
    assert r.returncode == 1 and "shape.json" in r.stderr and "Traceback" not in r.stderr
    (tmp_path / "shape.json").write_text(json.dumps({"file": "door.json"}))
    r = run(cwd=tmp_path)
    assert r.returncode == 1 and "list" in r.stderr


@pytest.mark.parametrize("bad", [
    "[]", "null", "3", '"door"', '{"machines": 4}', '{"machines": [1, "a", null]}', '[{"id": "x"}]',
    '{"id": "x", "initial": "a", "states": {"a": {"on": {"go": [[["b"]]]}}}}',
    '{"id": "x", "initial": "a", "states": {"a": {"on": {"go": {"target": "a", "guard": {"name": []}}}}}}',
    '{"id": ["x"], "initial": {"a": 1}, "states": [1]}',
    '{"id": "x", "initial": "a", "states": {"a": {"on": {"go": {"target": "b", "guard": {"name": "g", "source": 5}}}}}}',
])
def test_no_wrong_json_ends_in_a_traceback(tmp_path, bad):
    (tmp_path / "bad.json").write_text(bad)
    for args in (("--file", "bad.json"), ("x", "--file", "bad.json"), ("--check", "--file", "bad.json")):
        r = run(*args, cwd=tmp_path)
        assert "Traceback" not in r.stderr, (args, r.stderr)
        assert r.returncode in (0, 1, 2)


# ---- shape --check ----

def test_check_says_ok_for_each_program_that_is_fine(home):
    r = run("--check", cwd=home)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "demo.door" in r.stdout and "demo.lamp" in r.stdout and r.stdout.count("ok") >= 2
    assert "2 programs checked" in r.stdout


def test_check_lists_every_problem_and_exits_1(home):
    broken = dict(DOOR, id="demo.broken", states={"closed": {"on": {"push": {"guard": "g"}, "jam": 3}}})
    (home / "broken.json").write_text(json.dumps(broken))
    (home / "shape.json").write_text(json.dumps([{"file": "door.json"}, {"file": "broken.json"}, {"file": "gone.json"}]))
    r = run("--check", cwd=home)
    assert r.returncode == 1
    assert "demo.door" in r.stdout and "2 problems" in r.stdout
    assert 'event "push"' in r.stdout and 'event "jam"' in r.stdout and "gone.json" in r.stdout


def test_check_prints_notes_and_still_exits_0(home):
    noted = dict(DOOR, attention=["stuck", "burning"])
    (home / "door.json").write_text(json.dumps(noted))
    r = run("--check", "door", cwd=home)
    assert r.returncode == 0, r.stdout
    assert "note" in r.stdout and '"burning"' in r.stdout
    assert "demo.lamp" not in r.stdout


def test_the_summary_counts_the_notes_and_does_not_call_them_fine(home):
    (home / "door.json").write_text(json.dumps(dict(DOOR, attention=["stuck", "burning"], about=None)))
    r = run("--check", cwd=home)
    assert r.returncode == 0
    last = r.stdout.strip().splitlines()[-1]
    assert last == "2 programs checked: no problems, and 2 notes."


def test_the_summary_when_nothing_could_be_read(tmp_path):
    (tmp_path / "shape.json").write_text(json.dumps([{"file": "gone.json"}]))
    r = run("--check", cwd=tmp_path)
    assert r.returncode == 1
    assert r.stdout.strip().splitlines()[-1] == "No program was checked. 1 source could not be read."


def test_check_with_a_name_nothing_has_exits_2(home):
    r = run("--check", "nope", cwd=home)
    assert r.returncode == 2 and "nothing is called" in r.stderr


# ---- the screen ----

def test_on_a_real_terminal_it_stays_open_until_q(home):
    with Terminal(SHAPE, cwd=str(home)) as term:
        first = term.read_for(2.0)
        assert term.running(), "shape closed by itself: %r" % first[-300:]
        assert "demo.door" in first and "PROGRAM" in first and "enter" in first
        term.press(b"\r")
        second = term.read_for(1.5)
        assert term.running()
        assert "· start" in second and "esc" in second
        term.press(b"q")
        assert term.wait() == 0


def test_the_screen_says_when_it_shows_the_examples(tmp_path):
    with Terminal(SHAPE, cwd=str(tmp_path)) as term:
        first = term.read_for(2.0)
        assert "These are the examples that come with shape" in first and "coffee.machine" in first
        term.press(b"q")
        assert term.wait() == 0
