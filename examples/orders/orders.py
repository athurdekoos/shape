#!/usr/bin/env python3
"""orders: a small program that runs through its own table of moves.

    python3 orders.py            run four made-up orders and print each move
    python3 orders.py --shape    print the table as JSON, which is what shape reads

The table is MACHINE. The program never decides for itself which state comes next: each
function in WORK does the work of one state and says what happened, and MACHINE.step looks
up where that leads. So the JSON that --shape prints is the program, not a drawing of it.
"""
import os
import sys

# In your own project, copy python/shapetable.py beside your code and drop these two lines.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python"))

from shapetable import Machine, T  # noqa: E402


# ---- the conditions: each one's first sentence is shown by shape ----

def is_declined(order):
    """The bank refused the card."""
    return order["card"] == "declined"


def can_try_again(order):
    """The bank did not answer, and the order has been tried fewer than three times."""
    return order["card"] == "slow" and order["tries"] < 3


# ---- the table ----

MACHINE = Machine(
    "orders.fulfil", initial="new", goal="shipped",
    about="Takes one order from the basket to the door: payment, packing and the parcel.",
    attention=["declined", "failed"],
    transitions=[
        T("submit",       "new",       "submitted",    "paying"),
        T("paid",         "paying",    "paid",         "packing"),
        T("declined",     "paying",    "error",        "declined", guard=is_declined, output="email_customer"),
        T("try_again",    "paying",    "error",        "paying",   guard=can_try_again),
        T("pay_failed",   "paying",    "error",        "failed"),
        T("packed",       "packing",   "packed",       "shipped",  output="print_label"),
        T("out_of_stock", "packing",   "out_of_stock", "refunding"),
        T("refunded",     "refunding", "refunded",     "refunded", output="email_customer"),
    ])


# ---- the work of each state: do it, then say what happened ----

def submit(order):
    return "submitted"


def charge(order):
    order["tries"] += 1
    return "paid" if order["card"] == "good" else "error"


def pack(order):
    return "packed" if order["in_stock"] else "out_of_stock"


def refund(order):
    return "refunded"


WORK = {"new": submit, "paying": charge, "packing": pack, "refunding": refund}


def fulfil(order) -> str:
    """Run one order to an end state and return that state."""
    state = MACHINE.initial
    while state in WORK:
        event = WORK[state](order)
        move = MACHINE.step(state, event, order)
        print("    %-10s %-13s -> %s" % (state, event, move.target))
        state = move.target
    return state


def main(argv) -> int:
    if "--shape" in argv:
        MACHINE.print_json()
        return 0
    orders = [("a book, paid by a good card", {"card": "good", "in_stock": True}),
              ("a lamp, paid by a card the bank refuses", {"card": "declined", "in_stock": True}),
              ("a chair that is out of stock", {"card": "good", "in_stock": False}),
              ("a kettle, while the bank does not answer", {"card": "slow", "in_stock": True})]
    for name, order in orders:
        print(name)
        end = fulfil(dict(order, tries=0))
        print("    ends in %s" % end)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
