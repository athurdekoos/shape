"""Tests for shapetable, the one file a Python program copies to keep its moves in a table,
run through the table, and print it for shape."""
import io
import json

import pytest

import shapetable as st
import shapeview as sv


def is_declined(order):
    """The bank refused the card.

    A second paragraph that is not printed.
    """
    return order.get("card") == "declined"


def is_slow(order):
    return order.get("card") == "slow"


def machine(**over):
    args = dict(initial="new", goal="shipped", about="Takes one order to the door.", attention=["declined", "failed"],
                transitions=[
                    st.T("submit", "new", "submitted", "paying"),
                    st.T("declined", "paying", "error", "declined", guard=is_declined),
                    st.T("again", "paying", "error", "paying", guard=is_slow, output="wait"),
                    st.T("failed", "paying", "error", "failed"),
                    st.T("paid", "paying", "paid", "shipped"),
                ])
    args.update(over)
    return st.Machine("orders.fulfil", **args)


def test_step_gives_the_first_move_whose_condition_holds():
    m = machine()
    assert m.step("new", "submitted").target == "paying"
    assert m.step("paying", "error", {"card": "declined"}).id == "declined"
    assert m.step("paying", "error", {"card": "slow"}).output == "wait"
    assert m.step("paying", "error", {"card": "lost"}).target == "failed"


def test_an_event_the_state_does_not_take_is_an_error():
    with pytest.raises(st.NoTransition, match="shipped"):
        machine().step("shipped", "submitted")


def test_a_table_with_a_mistake_is_refused_when_it_is_made():
    with pytest.raises(ValueError, match="twice"):
        machine(transitions=[st.T("a", "new", "go", "x"), st.T("a", "x", "go", "new")], goal=None, attention=[])
    with pytest.raises(ValueError, match="nowhere"):
        machine(initial="nowhere")
    with pytest.raises(ValueError, match="heaven"):
        machine(goal="heaven")
    with pytest.raises(ValueError, match="burning"):
        machine(attention=["burning"])


def test_the_json_is_what_shape_reads():
    doc = machine().to_json()
    assert doc["id"] == "orders.fulfil" and doc["initial"] == "new" and doc["goal"] == "shipped"
    assert doc["about"] == "Takes one order to the door." and doc["attention"] == ["declined", "failed"]
    assert doc["defined_in"].endswith("test_shapetable.py")
    assert list(doc["states"]) == ["new", "paying", "declined", "failed", "shipped"]
    error = doc["states"]["paying"]["on"]["error"]
    assert [b["target"] for b in error] == ["declined", "paying", "failed"]
    assert error[0]["guard"]["name"] == "is_declined"
    assert error[0]["guard"]["says"] == "The bank refused the card."
    assert error[0]["guard"]["source"].rsplit(":", 1)[0].endswith("test_shapetable.py")
    assert "says" not in error[1]["guard"] and error[1]["actions"] == ["wait"]
    assert "guard" not in error[2]
    assert doc["states"]["shipped"] == {"on": {}}

    built = sv.build(doc)
    assert [s["name"] for s in built["states"]] == ["new", "paying", "shipped", "declined", "failed"]
    assert sv.notes(built) == ['the condition "is_slow" has no sentence: give its guard a "says", or its Python '
                               'function a docstring']


def test_printing_gives_one_description_or_a_list_of_them():
    out = io.StringIO()
    machine().print_json(out)
    assert json.loads(out.getvalue())["id"] == "orders.fulfil"
    out = io.StringIO()
    st.dump([machine(), st.Machine("other", "a", [st.T("t", "a", "go", "b")])], out)
    assert [d["id"] for d in json.loads(out.getvalue())["machines"]] == ["orders.fulfil", "other"]
