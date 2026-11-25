"""Tests for the format: the shorthands, the problems a wrong description is refused with,
and the notes that are advice only."""
import pytest

import shapeformat as sf
import shapeview as sv
from screen import to_text


def doc(**over):
    base = {"id": "demo.door", "initial": "closed", "about": "A door.", "attention": ["stuck"],
            "states": {"closed": {"on": {"push": "open", "jam": "stuck"}}, "open": {}, "stuck": {}}}
    base.update(over)
    return base


def text(d):
    return to_text(sv.render(sv.build(d)), color=False)


# ---- shorthands ----

def test_an_event_may_name_its_target_as_a_string():
    read = sf.read(doc())
    assert read["states"]["closed"]["on"]["push"] == [{"id": None, "target": "open", "guard": None, "actions": [],
                                                       "where": 'state "closed", event "push"'}]
    assert "      push → open" in text(doc())


def test_an_event_may_hold_one_branch_or_a_list_of_branches_and_names():
    d = doc(states={"closed": {"on": {"push": {"target": "open", "actions": "creak"},
                                      "jam": [{"target": "stuck", "guard": "is_rusty"}, "closed"]}},
                    "open": None, "stuck": {}})
    read = sf.read(d)
    assert read["states"]["closed"]["on"]["push"][0]["actions"] == ["creak"]
    jam = read["states"]["closed"]["on"]["jam"]
    assert jam[0]["guard"] == {"name": "is_rusty", "source": "", "says": ""}
    assert jam[1]["target"] == "closed" and jam[1]["guard"] is None
    out = text(d)
    assert "      push → open · creak" in out
    assert "        ├ if is_rusty → stuck !" in out and "        └ otherwise → closed" in out


def test_a_state_with_nothing_under_it_is_an_end():
    for body in ({}, None, {"on": {}}):
        built = sv.build(doc(states={"closed": {"on": {"push": "open"}}, "open": body}, attention=[]))
        assert [s["end"] for s in built["states"]] == [False, True]


def test_a_condition_may_carry_its_own_sentence():
    d = doc(states={"closed": {"on": {"jam": [{"target": "stuck", "guard": {"name": "is_rusty", "says": "The hinge is rusty."}},
                                              "closed"]}}, "stuck": {}})
    built = sv.build(d)
    assert built["conditions"] == [{"name": "is_rusty", "where": "", "says": "The hinge is rusty."}]
    assert "is_rusty   The hinge is rusty." in text(d)


def test_the_sentence_in_the_json_wins_over_the_one_in_the_file(tmp_path):
    (tmp_path / "conds.py").write_text('def is_rusty(ctx):\n    """From the file."""\n    return True\n')
    guard = {"name": "is_rusty", "source": "conds.py:1"}
    states = {"closed": {"on": {"jam": [{"target": "stuck", "guard": guard}, "closed"]}}, "stuck": {}}
    assert sv.build(doc(states=states), root=str(tmp_path))["conditions"][0]["says"] == "From the file."
    guard["says"] = "From the JSON."
    assert sv.build(doc(states=states), root=str(tmp_path))["conditions"][0]["says"] == "From the JSON."


# ---- what is refused ----

def problems(d):
    with pytest.raises(sf.FormatError) as caught:
        sf.read(d)
    return caught.value.problems


def test_a_format_error_is_a_value_error_and_names_the_program():
    with pytest.raises(ValueError, match="demo.door"):
        sv.build(doc(initial="gone"))


def test_every_problem_is_reported_at_once():
    found = problems({"id": "x", "states": {"a": {"on": {"go": {"guard": "g"}, "stop": 3}}, "b": "end"}})
    assert len(found) == 4
    joined = "\n".join(found)
    assert '"initial"' in joined
    assert 'state "a", event "go"' in joined and '"target"' in joined
    assert 'state "a", event "stop"' in joined
    assert 'state "b"' in joined


@pytest.mark.parametrize("bad, word", [
    ([1, 2], "a list"),
    ("door", "a string"),
    (None, "null"),
    (7, "a number"),
])
def test_a_description_that_is_not_an_object_is_refused(bad, word):
    assert word in problems(bad)[0]


@pytest.mark.parametrize("change, word", [
    ({"id": ""}, '"id"'),
    ({"id": 5}, '"id"'),
    ({"states": {}}, '"states"'),
    ({"states": ["closed", "open"]}, '"states"'),
    ({"states": {"closed": {"on": ["push"]}}}, '"on"'),
    ({"states": {"closed": {"on": {"push": []}}}}, "no branch"),
    ({"states": {"closed": {"on": {"push": {"target": 4}}}}}, '"target"'),
    ({"states": {"closed": {"on": {"push": {"target": "open", "guard": {"source": "a.py:1"}}}}, "open": {}}}, '"name"'),
    ({"states": {"closed": {"on": {"push": {"target": "open", "guard": 9}}}, "open": {}}}, "guard"),
    ({"states": {"closed": {"on": {"push": {"target": "open", "actions": [1]}}}, "open": {}}}, '"actions"'),
    ({"attention": "stuck"}, '"attention"'),
    ({"goal": ["open"]}, '"goal"'),
    ({"about": 3}, '"about"'),
])
def test_each_wrong_part_is_named(change, word):
    assert any(word in p for p in problems(doc(**change))), problems(doc(**change))


def test_a_description_names_at_most_2000_states_and_has_at_most_20000_branches():
    assert sf.STATE_LIMIT == 2000 and sf.BRANCH_LIMIT == 20000
    ends = {"s%d" % i: {} for i in range(1, sf.STATE_LIMIT)}
    fine = {"id": "x", "initial": "s0", "states": dict(ends, s0={"on": {"go": "s1"}})}
    sf.read(fine)
    too_many = dict(fine, states=dict(fine["states"], s0={"on": {"go": "s1", "away": "s2000"}}))
    assert problems(too_many) == ["it names 2,001 states, and a description may name at most 2,000"]
    branches = {"id": "x", "initial": "a", "states": {"a": {"on": {"e%d" % i: "a" for i in range(sf.BRANCH_LIMIT + 1)}}}}
    assert problems(branches) == ["it has 20,001 branches, and a description may have at most 20,000"]


def test_in_a_list_of_branches_the_wrong_one_is_numbered():
    found = problems(doc(states={"closed": {"on": {"push": ["open", {"guard": "g"}]}}, "open": {}}))
    assert 'state "closed", event "push", branch 2' in found[0]


# ---- notes: advice that refuses nothing ----

def notes(d):
    return sv.notes(sv.build(d))


def test_a_clean_description_has_no_notes():
    assert notes(doc()) == []


@pytest.mark.parametrize("change, word", [
    ({"states": {"closed": {"on": {"push": "open", "jam": "stuck"}}, "stuck": {}}}, 'no entry under "states"'),
    ({"attention": ["stuck", "burning"]}, '"burning"'),
    ({"goal": "heaven"}, '"heaven"'),
    ({"states": {"closed": {"on": {"push": "open", "jam": "stuck"}}, "open": {}, "stuck": {}, "attic": {}}}, "never reached"),
    ({"states": {"closed": {"on": {"push": ["open", {"target": "stuck", "guard": "g"}]}}, "open": {}, "stuck": {}}}, "never tried"),
    ({"states": {"closed": {"on": {"push": {"target": "open", "guard": {"name": "g", "says": "It is light."}},
                                   "jam": "stuck"}}, "open": {}, "stuck": {}}}, "when none holds"),
    ({"about": None}, '"about"'),
    ({"attention": None}, '"attention"'),
    ({"atention": ["stuck"]}, '"atention"'),
    ({"states": {"closed": {"on": {"push": [{"target": "open", "guard": "is_light"}, "stuck"]}}, "open": {}, "stuck": {}}},
     'condition "is_light"'),
    ({"states": {"closed": {"on": {"push": {"id": "t1", "target": "open"}, "jam": {"id": "t1", "target": "stuck"}}},
                 "open": {}, "stuck": {}}}, '"t1"'),
])
def test_each_note(change, word):
    found = notes(doc(**change))
    assert any(word in n for n in found), found


def test_a_key_shape_does_not_read_is_noted_wherever_it_is():
    states = {"closed": {"On": {"push": "open"}, "on": {"push": {"target": "open", "cond": "is_light"},
                                                        "jam": {"target": "stuck", "guard": {"name": "g", "say": "It is."}}}},
              "open": {}, "stuck": {}}
    found = notes(doc(states=states))
    assert 'state "closed" has a key shape does not read: "On"' in found
    assert 'state "closed", event "push": the branch has a key shape does not read: "cond"' in found
    assert 'state "closed", event "jam": the guard has a key shape does not read: "say"' in found


def test_the_note_about_a_repeated_id_says_where_each_one_is():
    states = {"closed": {"on": {"push": {"id": "t1", "target": "open"}, "jam": {"id": "t1", "target": "stuck"}}},
              "open": {}, "stuck": {}}
    found = [n for n in notes(doc(states=states)) if '"t1"' in n]
    assert found == ['the id "t1" is given to more than one branch: state "closed", event "push" and '
                     'state "closed", event "jam"']


def test_the_note_about_a_condition_names_the_key_to_add():
    states = {"closed": {"on": {"push": [{"target": "open", "guard": "is_light"}, "stuck"]}}, "open": {}, "stuck": {}}
    assert any('"says"' in n for n in notes(doc(states=states)))
