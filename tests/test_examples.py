"""Tests for the examples: each one is fine by shape --check, and the two that are programs
really run through the table they print."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import shapeformat as sf
import shapeview as sv
from screen import sources

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "examples"
SHAPE = REPO / "bin" / "shape"
NODE = shutil.which("node")
MOVE = re.compile(r"^\s+(\S+)\s+(\S+)\s+->\s+(\S+)\s*$")


def out(*argv, cwd=EX):
    r = subprocess.run(list(argv), capture_output=True, text=True, cwd=cwd)
    assert r.returncode == 0, r.stderr
    return r.stdout


def moves_in(doc):
    return {(state, event, b["target"]) for state, body in sf.read(doc)["states"].items()
            for event, branches in body["on"].items() for b in branches}


def test_the_examples_list_names_three_programs_in_three_forms():
    listed = sources(str(EX / "shape.json"))
    assert [sorted(s)[0] for s in listed] == ["file", "command", "command"]


def test_every_example_is_fine_by_check():
    r = subprocess.run([sys.executable, str(SHAPE), "--check", "--config", str(EX / "shape.json")],
                       capture_output=True, text=True)
    if NODE is None:
        assert "coffee.machine" in r.stdout and "orders.fulfil" in r.stdout
        pytest.skip("node is not installed, so the JavaScript example could not be read")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "3 programs checked" in r.stdout and "note" not in r.stdout and "problem" not in r.stdout


def test_the_python_example_takes_only_moves_that_are_in_its_table():
    doc = json.loads(out(sys.executable, "orders/orders.py", "--shape"))
    table = moves_in(doc)
    taken = [m.groups() for m in map(MOVE.match, out(sys.executable, "orders/orders.py").splitlines()) if m]
    assert len(taken) >= 8
    assert set(taken) <= table
    ends = {s for s, body in sf.read(doc)["states"].items() if not body["on"]}
    assert {t[2] for t in taken} & ends >= {"shipped", "declined", "refunded"}


def test_the_python_example_has_no_second_copy_of_its_moves():
    """The state in orders.py is only ever set from the table: to MACHINE.initial at the start, and
    after that to the target of the move that MACHINE.step gave."""
    import ast
    tree = ast.parse((EX / "orders" / "orders.py").read_text())
    set_to = [ast.unparse(n.value) for n in ast.walk(tree)
              if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "state"]
    assert sorted(set_to) == ["MACHINE.initial", "move.target"]
    moves = [ast.unparse(n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "move"]
    assert moves == ["MACHINE.step(state, event, order)"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_javascript_example_takes_only_moves_that_are_in_its_table():
    doc = json.loads(out("node", "download/download.js", "--shape"))
    table = moves_in(doc)
    taken = [m.groups() for m in map(MOVE.match, out("node", "download/download.js").splitlines()) if m]
    assert len(taken) >= 6 and set(taken) <= table
    built = sv.build(doc)
    assert sv.notes(built) == []
    assert all(c["says"] for c in built["conditions"])


def test_the_hand_written_example_uses_the_shorthands():
    doc = json.loads((EX / "coffee" / "coffee.json").read_text())
    kinds = {type(v) for body in doc["states"].values() for v in ((body or {}).get("on") or {}).values()}
    assert str in kinds and list in kinds


def test_the_readme_shows_what_shape_really_prints():
    readme = (REPO / "README.md").read_text()
    block = readme.split("<!-- shape coffee --plain -->", 1)[1].split("```", 2)[1]
    block = block.split("\n", 1)[1]
    real = out(sys.executable, str(SHAPE), "coffee", "--config", str(EX / "shape.json"))
    assert block.strip() == real.strip()


def test_the_schema_agrees_with_the_examples_and_with_read():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "schema" / "shape.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    check = jsonschema.Draft202012Validator(schema)
    docs = [json.loads((EX / "coffee" / "coffee.json").read_text()),
            json.loads(out(sys.executable, "orders/orders.py", "--shape"))]
    if NODE:
        docs.append(json.loads(out("node", "download/download.js", "--shape")))
    for doc in docs:
        assert list(check.iter_errors(doc)) == [], doc["id"]
    for bad in ({"id": "x", "states": {}}, {"id": "x", "initial": "a", "states": {"a": {"on": {"go": {"guard": "g"}}}}},
                {"id": "x", "initial": "a", "states": {"a": {"on": ["go"]}}}, [1, 2]):
        assert list(check.iter_errors(bad)), bad
        with pytest.raises(sf.FormatError):
            sf.read(bad)
