"""Tests for the shape command: where it finds the programs, what it prints, and what it
says when something is wrong."""
import json
import os
import shutil
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


# ---- what shape runs ----

def marker_program(path, marker):
    """A program that prints LAMP and leaves a file behind, so a test can tell that it ran."""
    path.write_text("import json, pathlib\npathlib.Path(%r).write_text('ran')\nprint(json.dumps(%r))\n"
                    % (str(marker), LAMP))


def test_a_shape_json_that_anyone_can_change_does_not_run_its_commands(home):
    ran = home / "ran.txt"
    marker_program(home / "lamp.py", ran)
    os.chmod(home / "shape.json", 0o666)
    r = run("--check", cwd=home)
    assert not ran.exists()
    assert r.returncode == 1 and "demo.door" in r.stdout
    assert "anyone on this computer can change" in r.stdout and "shape --config" in r.stdout
    listing = run(cwd=home)
    assert not ran.exists() and "Could not read" in listing.stdout and "demo.door" in listing.stdout
    assert run("--check", "--config", "shape.json", cwd=home).returncode == 0 and ran.exists()


def test_a_shape_json_another_user_owns_does_not_run_its_commands(home, monkeypatch, capsys):
    import shapeview as sv
    ran = home / "ran.txt"
    marker_program(home / "lamp.py", ran)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(home / "shape.json").st_uid + 1, raising=False)
    code = sv.main(["--check"], home=str(REPO), cwd=str(home), environ={})
    out = capsys.readouterr().out
    assert not ran.exists() and code == 1
    assert "belongs to another user" in out and "shape --config" in out
    code = sv.main(["--check"], home=str(REPO), cwd=str(home), environ={"SHAPE_CONFIG": str(home / "shape.json")})
    assert code == 0 and ran.exists()


@pytest.mark.skipif(shutil.which("python3") is None, reason="python3 is not on the PATH")
def test_a_bare_command_name_is_never_a_file_in_the_project(home):
    ran = home / "ran.txt"
    planted = home / "python3"
    planted.write_text("#!/bin/sh\necho planted > '%s'\n" % ran)
    planted.chmod(0o755)
    (home / "shape.json").write_text(json.dumps([{"command": ["python3", "lamp.py"]}]))
    r = run("--check", cwd=home)
    assert not ran.exists()
    assert r.returncode == 0 and "demo.lamp" in r.stdout, r.stdout


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


ODD = {"id": "odd.one", "initial": "a", "about": "x\u001b]0;pwned\u0007\u001b[2Khidden", "attention": [],
       "states": {"a": {"on": {"go": "a\u0000b"}}, "a\u0000b": {}}}


def test_control_characters_in_a_description_are_not_sent_to_the_terminal(tmp_path):
    (tmp_path / "odd.json").write_text(json.dumps(ODD))
    for args in (("--plain",), ("--check",)):
        r = run("--file", "odd.json", *args, cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert "\x1b" not in r.stdout and "\x00" not in r.stdout and "\x07" not in r.stdout
    outline = run("--file", "odd.json", "--plain", cwd=tmp_path).stdout
    assert "x?]0;pwned??[2Khidden" in outline and "go → a?b" in outline


def test_text_python_cannot_encode_does_not_stop_the_output(tmp_path):
    (tmp_path / "s.json").write_text('{"id": "s\\ud800", "initial": "a", "about": "A.", "attention": [], "states": {"a": {}}}')
    for args in (("--plain",), ("--check",)):
        r = run("--file", "s.json", *args, cwd=tmp_path)
        assert r.returncode == 0 and "Traceback" not in r.stderr, r.stderr
        assert "s?" in r.stdout
    ascii_only = run("coffee", "--plain", env={"PYTHONIOENCODING": "ascii"}, cwd=tmp_path)
    assert ascii_only.returncode == 0 and "Traceback" not in ascii_only.stderr, ascii_only.stderr
    assert "? idle ? start" in ascii_only.stdout


def test_a_pipe_that_closes_early_ends_quietly(tmp_path):
    ends = {"a_rather_long_name_for_an_end_state_%04d" % i: {} for i in range(1900)}
    many = {"id": "many.ends", "initial": "s", "about": "Many ends.", "attention": [],
            "states": dict({"s": {"on": {"e%d" % i: name for i, name in enumerate(ends)}}}, **ends)}
    (tmp_path / "many.json").write_text(json.dumps(many))
    p = subprocess.Popen([sys.executable, str(SHAPE), "--file", "many.json", "--plain", "--all"], cwd=tmp_path,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.stdout.close()            # the reader goes away before shape has printed, as with | head
    err = p.stderr.read().decode()
    p.stderr.close()
    assert p.wait(timeout=30) == 0, err
    assert err == ""


def test_version():
    r = run("--version")
    assert r.returncode == 0 and r.stdout.startswith("shape ")


def test_the_help_says_where_counting_stops():
    r = run("--help")
    assert r.returncode == 0 and "every route that was found" in r.stdout and "2,000" in r.stdout
    assert "however many" not in r.stdout


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


TWICE = '{"id": "x", "initial": "a", "states": {"a": {"on": {"error": "b", "go": "b", "error": "a"}}, "b": {}}}'


@pytest.mark.parametrize("sources, words", [
    ([{"file": "deep.json"}], "nested too deeply"),
    ([{"command": [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff')"]}], "its output is not UTF-8 text"),
    ([{"file": "latin.json"}], "is not UTF-8 text"),
    ([{"file": "a\u0000b.json"}], "NUL character"),
    ([{"command": ["python3\u0000"]}], "NUL character"),
    ([{"file": "door.json", "registry": "r\u0000.json"}], "NUL character"),
    ([{"file": "door.json", "registry": 7}], '"registry"'),
    ([{"command": [""]}], 'a "command" is a list of words'),
    ([{"command": ["python3", 3]}], 'a "command" is a list of words'),
    ([{"command": []}], 'a "command" is a list of words'),
    ([{"command": "python3 orders.py"}], 'a "command" is a list of words'),
    ([{"file": "twice.json"}], 'the key "error" is written twice in one object'),
])
def test_a_source_that_cannot_be_read_is_a_sentence(tmp_path, sources, words):
    (tmp_path / "deep.json").write_text("[" * 100000 + "]" * 100000)
    (tmp_path / "latin.json").write_bytes(b'{"id": "caf\xe9"}')
    (tmp_path / "twice.json").write_text(TWICE)
    (tmp_path / "door.json").write_text(json.dumps(DOOR))
    (tmp_path / "shape.json").write_text(json.dumps(sources))
    for args in (("--check",), ()):
        r = run(*args, cwd=tmp_path)
        assert "Traceback" not in r.stderr, r.stderr
        assert words in r.stdout + r.stderr, r.stdout + r.stderr
    assert run("--check", cwd=tmp_path).returncode == 1


def test_a_file_or_a_shape_json_too_deep_or_with_a_key_twice_is_a_sentence(tmp_path):
    (tmp_path / "deep.json").write_text("[" * 100000 + "]" * 100000)
    (tmp_path / "twice.json").write_text(TWICE)
    for name, words in (("deep.json", "nested too deeply"), ("twice.json", '"error" is written twice')):
        r = run("--check", "--file", name, cwd=tmp_path)
        assert r.returncode == 1 and words in r.stdout + r.stderr and "Traceback" not in r.stderr, r.stderr
        (tmp_path / "shape.json").write_text((tmp_path / name).read_text())
        r = run(cwd=tmp_path)
        assert r.returncode == 1 and words in r.stderr and "Traceback" not in r.stderr, r.stderr
    (tmp_path / "shape.json").write_text('[{"file": "a.json", "file": "b.json"}]')
    assert '"file" is written twice' in run(cwd=tmp_path).stderr


def test_standard_input_that_is_not_utf8_is_a_sentence(tmp_path):
    r = subprocess.run([sys.executable, str(SHAPE), "--check", "--file", "-"], input=b'{"id": "caf\xe9"}',
                       capture_output=True, cwd=tmp_path)
    assert r.returncode == 1 and b"standard input" in r.stdout + r.stderr and b"Traceback" not in r.stderr


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


def test_check_notes_a_key_of_a_source_that_shape_does_not_read(home):
    (home / "shape.json").write_text(json.dumps([{"file": "door.json", "regsitry": "reg.json"}]))
    r = run("--check", cwd=home)
    assert r.returncode == 0, r.stdout
    assert 'note: the source that lists it has a key shape does not read: "regsitry"' in r.stdout


def test_check_exits_1_when_a_source_cannot_be_read_even_if_the_rest_are_fine(home):
    (home / "shape.json").write_text(json.dumps([{"file": "door.json"}, {"file": "gone.json"}]))
    r = run("--check", cwd=home)
    assert r.returncode == 1
    assert r.stdout.strip().splitlines()[-1] == "1 program checked: it is fine. 1 source could not be read."


def test_check_takes_part_of_a_name_in_any_case(home):
    r = run("--check", "DOOR", cwd=home)
    assert r.returncode == 0 and "demo.door" in r.stdout and "demo.lamp" not in r.stdout


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


def test_the_screen_shows_control_characters_as_question_marks(tmp_path):
    (tmp_path / "odd.json").write_text(json.dumps(ODD))
    with Terminal(SHAPE, "--file", "odd.json", cwd=str(tmp_path)) as term:
        first = term.read_for(2.0)
        assert term.running(), "shape closed by itself: %r" % first[-300:]
        assert "pwned" in first and "\x07" not in first and "?]0;pwned" in first
        term.press(b"\x1b")
        term.read_for(0.5)
        term.press(b"\r")
        second = term.read_for(1.5)
        assert term.running(), second[-300:]
        assert "a?b" in second
        term.press(b"q")
        assert term.wait() == 0


def test_the_screen_says_when_it_shows_the_examples(tmp_path):
    with Terminal(SHAPE, cwd=str(tmp_path)) as term:
        first = term.read_for(2.0)
        assert "These are the examples that come with shape" in first and "coffee.machine" in first
        term.press(b"q")
        assert term.wait() == 0
