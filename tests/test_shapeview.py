"""Tests for shapeview: the outline model, its text, the JSON sources and the screen."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import shapeview as sv
from screen import SourceError, to_text, wrap

REPO = Path(__file__).resolve().parents[1]
SHAPE = REPO / "bin" / "shape"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def machine(id, initial, transitions, goal=None, attention=(), defined_in="demo/sync.py"):
    """A machine description in the JSON shape the programs print.
    Each transition is (id, source, event, target[, condition[, action]])."""
    states = {}
    for t in transitions:
        tid, source, event, target = t[:4]
        guard = t[4] if len(t) > 4 else None
        action = t[5] if len(t) > 5 else None
        branch = {"id": tid, "target": target}
        if guard:
            branch["guard"] = {"name": guard, "source": "conds.py:1"}
        if action:
            branch["actions"] = [action]
        states.setdefault(source, {"on": {}})["on"].setdefault(event, []).append(branch)
        states.setdefault(target, {"on": {}})
    doc = {"id": id, "initial": initial, "states": states, "defined_in": defined_in,
           "attention": list(attention)}
    if goal:
        doc["goal"] = goal
    return doc


def sync_doc():
    return machine("demo.sync", "idle", [
        ("start", "idle", "start", "working"),
        ("done", "working", "finished", "ok", None, "publish"),
        ("auth", "working", "error", "auth", "is_auth"),
        ("failed", "working", "error", "failed"),
        ("retry", "failed", "retry", "working"),
    ], goal="ok", attention=("auth", "failed"))


def model(doc=None):
    return sv.build(doc or sync_doc())


def text(m, **kw):
    return to_text(sv.render(m, **kw), color=False)


# ---- the model ----

def test_states_read_as_the_flow_first_then_the_endings():
    # failed leads back to working, so it is part of the flow; ok and auth are endings,
    # and the ending that needs attention comes last.
    assert [s["name"] for s in model()["states"]] == ["idle", "working", "failed", "ok", "auth"]


def test_endings_that_are_fine_come_before_endings_that_need_attention():
    built = sv.build(machine("ends", "a", [("x", "a", "bad", "broken"), ("y", "a", "good", "done")],
                             attention=["broken"]))
    assert [s["name"] for s in built["states"]] == ["a", "done", "broken"]
    assert [p["end"] for p in built["paths"]] == ["done", "broken"]


def test_start_end_goal_and_attention_are_marked():
    by = {s["name"]: s for s in model()["states"]}
    assert by["idle"]["start"] and not by["working"]["start"]
    assert by["ok"]["end"] and by["auth"]["end"] and not by["failed"]["end"]
    assert by["ok"]["goal"]
    assert by["auth"]["attention"] and by["failed"]["attention"] and not by["ok"]["attention"]


def test_branches_of_one_event_keep_their_declared_order():
    working = [s for s in model()["states"] if s["name"] == "working"][0]
    error = [e for e in working["events"] if e["event"] == "error"][0]
    assert [(b["guard"], b["target"]) for b in error["branches"]] == [("is_auth", "auth"), (None, "failed")]
    assert error["open"] is False
    finished = [e for e in working["events"] if e["event"] == "finished"][0]
    assert finished["branches"][0]["action"] == "publish"


def test_every_way_into_a_state_that_needs_attention_is_listed():
    wrong = [(w["source"], w["event"], w["guard"], w["target"]) for w in model()["wrong"]]
    assert wrong == [("working", "error", "is_auth", "auth"), ("working", "error", None, "failed")]


def test_staying_in_an_attention_state_is_not_a_new_way_in():
    built = sv.build(machine("alert", "ok", [
        ("a", "ok", "run_failed", "failing"),
        ("b", "failing", "run_failed", "failing"),
        ("c", "failing", "run_succeeded", "ok"),
    ], attention=["failing"]))
    assert [(w["source"], w["target"]) for w in built["wrong"]] == [("ok", "failing")]


def test_routes_run_from_the_start_to_each_end_without_repeating_a_state():
    m = model()
    assert [p["states"] for p in m["paths"]] == [["idle", "working", "ok"], ["idle", "working", "auth"]]
    assert m["path_total"] == 2 and m["paths_capped"] is False and m["endless"] is False
    assert [p["attention"] for p in m["paths"]] == [False, True]


def test_two_transitions_between_the_same_states_are_one_route_counted_twice():
    built = sv.build(machine("twice", "a", [("x", "a", "go", "b"), ("y", "a", "skip", "b"), ("z", "b", "end", "c")]))
    assert [(p["states"], p["ways"]) for p in built["paths"]] == [(["a", "b", "c"], 2)]
    assert built["path_total"] == 1
    out = text(built)
    assert "Routes from start to an end (1)" in out and "(2 ways)" in out


def test_a_transition_back_to_an_earlier_state_is_listed_as_going_back():
    assert [(b["source"], b["event"], b["target"]) for b in model()["loops"]] == [("failed", "retry", "working")]


def test_a_program_with_no_end_state_is_called_endless():
    built = sv.build(machine("alert", "ok", [("a", "ok", "fail", "failing"), ("b", "failing", "ok", "ok")],
                             attention=["failing"]))
    assert built["endless"] is True and built["paths"] == []
    assert "no end state" in text(built)


def test_counting_stops_at_the_limit_and_says_so():
    ts = []
    for i in range(12):  # twelve two-way forks in a row: 4096 routes
        ts += [("u%d" % i, "s%d" % i, "up", "u%d" % i), ("d%d" % i, "s%d" % i, "down", "d%d" % i),
               ("ju%d" % i, "u%d" % i, "join", "s%d" % (i + 1)), ("jd%d" % i, "d%d" % i, "join", "s%d" % (i + 1))]
    built = sv.build(machine("forks", "s0", ts))
    assert built["paths_capped"] is True
    assert "more than %d" % sv.PATH_LIMIT in text(built)


def test_a_long_chain_of_states_is_walked_without_running_out_of_stack():
    n = sv.shapeformat.STATE_LIMIT - 10
    built = sv.build(machine("chain", "s0", [("t%d" % i, "s%d" % i, "go", "s%d" % (i + 1)) for i in range(n)]))
    assert built["path_total"] == 1 and len(built["paths"][0]["states"]) == n + 1
    assert built["unreachable"] == []


def test_the_largest_description_allowed_is_shown_in_reasonable_time():
    import time
    states = sv.shapeformat.STATE_LIMIT
    per_state = sv.shapeformat.BRANCH_LIMIT // states
    doc = {"id": "big", "initial": "s0", "about": "A big one.", "attention": [],
           "states": {"s%d" % i: {"on": {"e%d" % j: "s%d" % ((i * 7 + j * 13) % states) for j in range(per_state)}}
                      for i in range(states)}}
    started = time.time()
    built = sv.build(doc)
    sv.notes(built)
    sv.render(built)
    assert time.time() - started < 20
    assert built["transitions"] == sv.shapeformat.BRANCH_LIMIT


def k10(first_move_to_the_end):
    """Ten states that all lead to each other, and from the start one move to an end, given first or last."""
    ts = [("k%d%d" % (i, j), "k%d" % i, "to%d" % j, "k%d" % j) for i in range(10) for j in range(10) if i != j]
    into = [("in", "s0", "enter", "k0")]
    out = [("finish", "s0", "finish", "done")]
    return machine("k10", "s0", (out + into if first_move_to_the_end else into + out) + ts)


def test_when_the_step_limit_stops_the_walk_before_any_route_the_count_says_so():
    built = sv.build(k10(first_move_to_the_end=False))
    assert built["paths_capped"] is True and built["path_total"] == 0
    out = text(built)
    assert "more than" not in out
    assert "too many routes to an end to count" in out.splitlines()[1]
    assert "Routes from start to an end (too many to count)" in out
    assert "The routes were too many to count" in out
    assert sv._row(built)[2] == "too many"


def test_when_the_step_limit_stops_the_walk_the_count_is_what_was_found_or_more():
    built = sv.build(k10(first_move_to_the_end=True))
    assert built["paths_capped"] is True and built["path_total"] == 1
    out = text(built)
    assert "more than" not in out
    assert "1 or more routes to an end" in out.splitlines()[1]
    assert "Routes from start to an end (1 or more)" in out and "s0 → done" in out
    assert sv._row(built)[2] == "1 or more"


def test_the_route_limit_counts_routes_and_not_ways():
    built = sv.build(machine("ways", "a", [("t%d" % i, "a", "e%d" % i, "b") for i in range(sv.PATH_LIMIT + 1)]))
    assert built["paths_capped"] is False and built["path_total"] == 1
    out = text(built)
    assert "1 route to an end" in out and "(%d ways)" % (sv.PATH_LIMIT + 1) in out and "more than" not in out


def test_all_prints_every_route_that_was_found():
    ts = []
    for i in range(12):  # twelve two-way forks in a row: 4096 routes
        ts += [("u%d" % i, "s%d" % i, "up", "u%d" % i), ("d%d" % i, "s%d" % i, "down", "d%d" % i),
               ("ju%d" % i, "u%d" % i, "join", "s%d" % (i + 1)), ("jd%d" % i, "d%d" % i, "join", "s%d" % (i + 1))]
    built = sv.build(machine("forks", "s0", ts))
    assert built["path_total"] == sv.PATH_LIMIT
    assert text(built, all_paths=True).count("s0 → ") == sv.PATH_LIMIT
    assert "more than %d routes to an end" % sv.PATH_LIMIT in text(built)


def test_a_branch_that_is_never_tried_leads_nowhere():
    doc = {"id": "door", "initial": "closed", "attention": ["stuck"],
           "states": {"closed": {"on": {"push": ["open", {"target": "stuck", "guard": {"name": "is_rusty", "says": "Rusty."}}],
                                        "kick": ["open", "closed"]}},
                      "open": {}, "stuck": {}}}
    built = sv.build(doc)
    assert built["wrong"] == [] and built["loops"] == []
    assert [p["states"] for p in built["paths"]] == [["closed", "open"]] and built["paths"][0]["ways"] == 2
    assert built["unreachable"] == ["stuck"]
    out = text(built)
    assert "Ways it goes wrong" not in out and "Goes back" not in out and "never reached" in out


def test_end_states_that_nothing_reaches_are_not_called_no_end_state():
    built = sv.build(machine("loop", "a", [("x", "a", "go", "b"), ("y", "b", "go", "a"), ("z", "c", "go", "d")]))
    assert built["endless"] is True
    out = text(built)
    assert "no end state" in out.splitlines()[1]
    assert "reaches no end state" in out and "has no end state" not in out


def test_two_conditions_with_one_name_and_two_sentences_are_both_listed():
    doc = {"id": "two", "initial": "a", "attention": [], "about": "Two.",
           "states": {"a": {"on": {"go": [{"target": "b", "guard": {"name": "g", "says": "First."}}, "c"],
                                   "run": [{"target": "c", "guard": {"name": "g", "says": "Second."}}, "b"],
                                   "fly": [{"target": "c", "guard": {"name": "g", "says": "First."}}, "b"]}},
                      "b": {}, "c": {}}}
    built = sv.build(doc)
    assert [c["says"] for c in built["conditions"]] == ["First.", "Second."]
    assert "Conditions (2)" in text(built)


def test_a_condition_gets_its_words_from_the_function_it_names(tmp_path):
    (tmp_path / "conds.py").write_text(
        'def is_auth(ctx):\n'
        '    """The error is an authentication failure.\n\n'
        '    A second paragraph that the outline leaves out.\n    """\n'
        '    return True\n')
    built = sv.build(sync_doc(), root=str(tmp_path))
    cond = built["conditions"][0]
    assert (cond["name"], cond["where"]) == ("is_auth", "conds.py:1")
    assert cond["says"] == "The error is an authentication failure."
    out = text(built)
    assert "    is_auth   The error is an authentication failure.\n              conds.py:1" in out


# ---- what describe() reads ----

DOCSTRING = 'def is_auth(ctx):\n    """Read from the file."""\n    return True\n'


def test_describe_reads_a_python_file_in_the_project(tmp_path):
    (tmp_path / "conds.py").write_text(DOCSTRING)
    assert sv.describe(str(tmp_path), "conds.py:1") == "Read from the file."


def test_describe_reads_nothing_outside_the_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (tmp_path / "conds.py").write_text(DOCSTRING)       # beside the project, not in it
    os.symlink(tmp_path / "conds.py", project / "link.py")
    assert sv.describe(str(project), "../conds.py:1") == ""
    assert sv.describe(str(project), str(tmp_path / "conds.py") + ":1") == ""
    assert sv.describe(str(project), "link.py:1") == ""


def test_describe_reads_only_a_regular_file_of_at_most_1_mb(tmp_path):
    import threading
    big = tmp_path / "big.py"
    big.write_text(DOCSTRING + "#" * (1024 * 1024) + "\n")
    assert sv.describe(str(tmp_path), "big.py:1") == ""
    if not hasattr(os, "mkfifo"):
        return
    os.mkfifo(str(tmp_path / "pipe.py"))
    said = []
    reader = threading.Thread(target=lambda: said.append(sv.describe(str(tmp_path), "pipe.py:1")), daemon=True)
    reader.start()
    reader.join(5)
    assert said == [""], "describe() waited on a named pipe"


def test_describe_needs_the_line_of_the_function_itself(tmp_path):
    (tmp_path / "conds.py").write_text("# the conditions\n\n" + DOCSTRING)
    assert sv.describe(str(tmp_path), "conds.py:3") == "Read from the file."
    for line in ("1", "2", "4", "\u00b2", "\u0663", "3.0", "", "x"):
        assert sv.describe(str(tmp_path), "conds.py:" + line) == "", line


def test_describe_survives_a_file_too_deep_to_parse(tmp_path):
    (tmp_path / "minus.py").write_text(DOCSTRING + "y = " + "-" * 100000 + "1\n")      # MemoryError
    assert sv.describe(str(tmp_path), "minus.py:1") == ""
    (tmp_path / "plus.py").write_text(DOCSTRING + "y = " + "+".join(["1"] * 50000) + "\n")  # RecursionError on 3.12+
    assert sv.describe(str(tmp_path), "plus.py:1") in ("", "Read from the file.")


def test_a_condition_whose_function_cannot_be_read_says_so():
    built = model()  # no root: conds.py does not exist
    assert built["conditions"][0]["says"] == ""
    assert "(no description written)" in text(built)


def test_an_event_whose_branches_all_have_conditions_is_open():
    built = sv.build(machine("open", "a", [("x", "a", "go", "b", "is_big")]))
    assert built["states"][0]["events"][0]["open"] is True
    out = text(built)
    assert "if is_big" in out and "otherwise no transition is declared" in out


def test_a_branch_after_an_unconditional_one_is_flagged_as_never_tried():
    built = sv.build(machine("shadow", "a", [("x", "a", "go", "b"), ("y", "a", "go", "c", "is_big")]))
    assert [b["never"] for b in built["states"][0]["events"][0]["branches"]] == [False, True]
    assert "never tried" in text(built)


def test_every_branch_after_one_with_no_condition_is_never_tried():
    built = sv.build(machine("shadow", "a", [("x", "a", "go", "b"), ("y", "a", "go", "c", "is_big"),
                                             ("z", "a", "go", "d", "is_small")]))
    assert [b["never"] for b in built["states"][0]["events"][0]["branches"]] == [False, True, True]


def test_a_state_nothing_leads_to_is_reported_as_never_reached():
    built = sv.build(machine("orphan", "a", [("x", "a", "go", "b"), ("y", "lost", "go", "b")]))
    assert built["unreachable"] == ["lost"]
    assert "Never reached" in text(built)


def test_a_description_that_is_not_a_machine_is_refused():
    with pytest.raises(ValueError, match="initial"):
        sv.build({"id": "x", "states": {}})
    with pytest.raises(ValueError, match="start state"):
        sv.build({"id": "x", "initial": "gone", "states": {"a": {"on": {}}}})


# ---- the text ----

def test_the_outline_reads_top_to_bottom():
    out = text(model())
    lines = out.splitlines()
    assert lines[0].startswith("demo.sync") and "demo/sync.py" in lines[0]
    assert "▶ idle · start" in out
    assert "      start → working" in out
    assert "      finished → ok · publish" in out
    assert "        ├ if is_auth → auth !" in out
    assert "        └ otherwise → failed !" in out
    assert "  ok · end · goal" in out
    assert "  auth · end · needs attention" in out
    assert out.index("▶ idle") < out.index("  working") < out.index("  ok · end")


def test_the_sections_follow_the_outline():
    out = text(model())
    for title in ("Ways it goes wrong (2)", "Routes from start to an end (2)", "Goes back (1)", "Conditions (1)"):
        assert title in out
    assert "idle → working → ok" in out
    assert "ends in auth, which needs attention" in out
    assert out.index("Ways it goes wrong") < out.index("Routes from start") < out.index("Conditions")


def test_long_route_lists_are_cut_with_a_count_unless_all_is_asked():
    ts = [("s", "a", "go", "hub")]
    for i in range(sv.PATHS_SHOWN + 3):  # more side trips to the same end than one screen shows
        ts += [("o%d" % i, "hub", "e%d" % i, "m%d" % i), ("b%d" % i, "m%d" % i, "back", "end")]
    built = sv.build(machine("many", "a", ts))
    short = text(built)
    assert "    and 3 more; add --all to print them" in short
    assert "and 3 more" not in text(built, all_paths=True)
    assert text(built, all_paths=True).count("a → hub → m") == sv.PATHS_SHOWN + 3


def test_plain_text_has_no_escape_codes_and_colour_text_does():
    lines = sv.render(model())
    assert not ANSI.search(to_text(lines, color=False))
    coloured = to_text(lines, color=True)
    assert ANSI.search(coloured)
    assert ANSI.sub("", coloured) == to_text(lines, color=False)


def test_control_characters_reach_the_terminal_as_question_marks():
    from screen import clean
    assert clean("a\x1b]0;x\x07b\x00c\x7f\x9bd\ud800e\tf\ng") == "a?]0;x?b?c??d?e?f?g"
    assert clean("▶ idle · start → é") == "▶ idle · start → é"
    lines = [[("x\x1b[2Khidden", None), (" ok", "dim")]]
    assert to_text(lines, color=False) == "x?[2Khidden ok\n"
    assert "\x1b[2K" not in to_text(lines, color=True)


# ---- where the JSON comes from ----

def write_sources(root, sources):
    """The sources as shape.json would list them; load_docs is given the list."""
    (root / "shape.json").write_text(json.dumps(sources))
    return sources


def load(root):
    from screen import sources
    return sv.load_docs(str(root), sources(str(root / "shape.json")))


def test_a_file_source_holds_one_machine_or_many(tmp_path):
    (tmp_path / "one.json").write_text(json.dumps(sync_doc()))
    (tmp_path / "many.json").write_text(json.dumps({"machines": [machine("b", "x", [("t", "x", "go", "y")])]}))
    write_sources(tmp_path, [{"file": "one.json"}, {"file": "many.json"}])
    assert [d["id"] for d in load(tmp_path)] == ["demo.sync", "b"]


def test_a_command_source_is_run_and_its_json_read(tmp_path):
    (tmp_path / "emit.py").write_text("import json\nprint(json.dumps(%r))\n" % {"machines": [sync_doc()]})
    write_sources(tmp_path, [{"command": [sys.executable, "emit.py"]}])
    assert [d["id"] for d in load(tmp_path)] == ["demo.sync"]


def test_a_registry_adds_the_attention_states_and_the_file(tmp_path):
    doc = sync_doc()
    del doc["attention"], doc["defined_in"]
    (tmp_path / "one.json").write_text(json.dumps(doc))
    (tmp_path / "reg.json").write_text(json.dumps([{"id": "demo.sync", "path": "prog/sync.py", "attention": ["auth"],
                                                    "about": "Copies the photos."}]))
    write_sources(tmp_path, [{"file": "one.json", "registry": "reg.json"}])
    got = load(tmp_path)[0]
    assert got["attention"] == ["auth"] and got["defined_in"] == "prog/sync.py"
    assert got["about"] == "Copies the photos."


def test_only_a_first_word_with_a_separator_is_looked_up_in_the_project(tmp_path):
    from screen import command_words
    (tmp_path / "python3").write_text("")
    assert command_words(str(tmp_path), ["python3", "emit.py"]) == ["python3", "emit.py"]
    assert command_words(str(tmp_path), ["tools/emit", "--shape"]) == [os.path.join(str(tmp_path), "tools/emit"),
                                                                     "--shape"]


def test_what_a_description_says_itself_wins_over_the_registry_unless_it_is_empty(tmp_path):
    doc = dict(sync_doc(), about="Its own sentence.")
    (tmp_path / "one.json").write_text(json.dumps(doc))
    (tmp_path / "reg.json").write_text(json.dumps([{"id": "demo.sync", "path": "elsewhere.py", "attention": ["auth"],
                                                    "about": "From the registry."}]))
    got = sv.load_docs(str(tmp_path), [{"file": "one.json", "registry": "reg.json"}])[0]
    assert got["attention"] == ["auth", "failed"] and got["defined_in"] == "demo/sync.py"
    assert got["about"] == "Its own sentence."
    (tmp_path / "one.json").write_text(json.dumps(dict(doc, about="", defined_in="")))
    got = sv.load_docs(str(tmp_path), [{"file": "one.json", "registry": "reg.json"}])[0]
    assert got["about"] == "From the registry." and got["defined_in"] == "elsewhere.py"


def test_the_list_shows_a_program_described_twice_once_and_says_so(tmp_path):
    (tmp_path / "one.json").write_text(json.dumps(sync_doc()))
    docs, failures = sv.load_all(str(tmp_path), [{"file": "one.json"}, {"file": "one.json"}])
    assert [d["id"] for d in docs] == ["demo.sync"]
    assert failures == ["demo.sync is described twice: by one.json and by one.json"]


def test_a_command_that_fails_is_reported_with_what_it_said(tmp_path):
    (tmp_path / "boom.py").write_text("import sys\nsys.stderr.write('no machines today')\nsys.exit(3)\n")
    write_sources(tmp_path, [{"command": [sys.executable, "boom.py"]}])
    with pytest.raises(SourceError, match="no machines today"):
        load(tmp_path)


def test_output_that_is_not_json_is_reported(tmp_path):
    (tmp_path / "bad.json").write_text("not json")
    write_sources(tmp_path, [{"file": "bad.json"}])
    with pytest.raises(SourceError, match="bad.json"):
        load(tmp_path)


def test_two_sources_may_not_describe_the_same_program(tmp_path):
    (tmp_path / "one.json").write_text(json.dumps(sync_doc()))
    write_sources(tmp_path, [{"file": "one.json"}, {"file": "one.json"}])
    with pytest.raises(SourceError, match="demo.sync"):
        load(tmp_path)


# ---- what a program is, in plain words ----

def about_doc():
    doc = sync_doc()
    doc["about"] = "Copies the photos to this computer."
    return doc


def test_the_outline_opens_with_what_the_program_is():
    lines = text(sv.build(about_doc())).splitlines()
    assert lines[1] == "Copies the photos to this computer."


# ---- long lines ----

def flat(lines):
    return ["".join(t for t, _ in line) for line in lines]


def test_a_long_line_is_wrapped_to_the_width_without_losing_a_word():
    line = [("    is_auth   ", "target"), ("The error is an authentication failure that needs a person to sign in again.", None)]
    wrapped = wrap(line, 40)
    rows = flat(wrapped)
    assert len(rows) > 1 and all(len(r) <= 40 for r in rows)
    assert " ".join(" ".join(rows).split()) == " ".join("".join(t for t, _ in line).split())
    assert rows[1].startswith(" " * 14) and not rows[1].startswith(" " * 15)   # under the sentence
    assert wrapped[0][0] == ("    is_auth   ", "target")


def test_a_sentence_from_the_margin_wraps_back_to_the_margin():
    rows = flat(wrap([("One run of the photo copier: checks, locks, copies and writes a log.", None)], 40))
    assert len(rows) == 2 and not rows[1].startswith(" ")


def test_a_short_line_is_left_alone():
    line = [("  ok", "state"), (" · end", "dim")]
    assert wrap(line, 40) == [line]


# ---- the screen that stays open ----

def browser(start=None):
    docs = [about_doc(), machine("b.other", "x", [("t", "x", "go", "y")]), machine("c.third", "p", [("t", "p", "go", "q")])]
    return sv.Browser([sv.build(d) for d in docs], start=start)


def screen(b, height=30, width=100):
    body, foot = b.frame(height, width)
    return "\n".join(flat(body)), foot


def test_it_opens_on_the_list_with_the_first_program_picked():
    b = browser()
    body, foot = screen(b)
    assert b.screen == "list" and not b.done
    for name in ("demo.sync", "b.other", "c.third"):
        assert name in body
    assert "> demo.sync" in body
    assert "Copies the photos to this computer." in body    # what the picked program is
    assert "enter" in foot and "q" in foot


def test_down_and_up_move_the_pick_and_stop_at_the_ends():
    b = browser()
    b.key("down")
    assert "> b.other" in screen(b)[0]
    b.key("down"), b.key("down"), b.key("down")
    assert "> c.third" in screen(b)[0]
    b.key("up"), b.key("up"), b.key("up"), b.key("up")
    assert "> demo.sync" in screen(b)[0]


def test_top_and_bottom_move_the_pick_to_the_ends_of_the_list():
    b = browser()
    b.key("bottom")
    assert "> c.third" in screen(b)[0]
    b.key("top")
    assert "> demo.sync" in screen(b)[0]


def test_enter_opens_the_picked_program_and_esc_comes_back():
    b = browser()
    b.key("down")
    b.key("open")
    body, foot = screen(b)
    assert b.screen == "outline"
    assert body.startswith("b.other") and "▶ x · start" in body
    assert "esc" in foot
    b.key("back")
    assert b.screen == "list" and "> b.other" in screen(b)[0]


def test_a_name_on_the_command_line_opens_that_program_first():
    b = browser(start=2)
    assert screen(b)[0].startswith("c.third")
    b.key("back")
    assert "> c.third" in screen(b)[0]


def test_the_outline_scrolls_and_stops_at_the_bottom():
    b = browser(start=0)
    top, _ = screen(b, height=8)
    assert top.startswith("demo.sync") and len(top.splitlines()) == 7       # one row is the key line
    b.key("down")
    assert not screen(b, height=8)[0].startswith("demo.sync")
    for _ in range(500):
        b.key("down")
    last = screen(b, height=8)[0].splitlines()
    assert last[-1].strip() == "conds.py:1"                                  # the outline's last line
    b.key("top")
    assert screen(b, height=8)[0].startswith("demo.sync")
    b.key("page_down", page=5)
    assert b.scroll == 5
    b.key("bottom")
    assert screen(b, height=8)[0].splitlines()[-1].strip() == "conds.py:1"


def test_a_cuts_and_restores_the_long_route_lists():
    ts = [("s", "a", "go", "hub")]
    for i in range(sv.PATHS_SHOWN + 3):
        ts += [("o%d" % i, "hub", "e%d" % i, "m%d" % i), ("b%d" % i, "m%d" % i, "back", "end")]
    b = sv.Browser([sv.build(machine("many", "a", ts))], start=0)
    assert "and 3 more" in screen(b, height=400)[0]
    b.key("all")
    assert "and 3 more" not in screen(b, height=400)[0]
    b.key("all")
    assert "and 3 more" in screen(b, height=400)[0]


def test_question_mark_explains_how_to_read_it_and_any_key_goes_back():
    b = browser(start=1)
    b.key("help")
    body, _ = screen(b, height=60)
    assert "How to read this" in body and "needs attention" in body
    b.key("down")
    assert b.screen == "outline" and screen(b)[0].startswith("b.other")


def test_q_closes_it_from_any_screen():
    for keys in ([], ["open"], ["help"]):
        b = browser()
        for k in keys:
            b.key(k)
        b.key("quit")
        assert b.done


def test_a_narrow_window_wraps_instead_of_cutting():
    b = sv.Browser([sv.build(about_doc())], start=0)
    body, _ = screen(b, height=200, width=30)
    assert all(len(row) <= 29 for row in body.splitlines())
    assert "Copies the photos to this" in body
