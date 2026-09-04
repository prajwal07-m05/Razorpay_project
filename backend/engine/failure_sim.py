"""Failure-mode simulation: remove a feed to prove the engine degrades safely.

mode="failure" drops the bank_credits feed, making settled-record
verification impossible. Pure Python.
"""


def apply_mode(tables, mode):
    """Return (tables_for_run, bank_feed_available).

    In failure mode the bank_credits feed is removed entirely; the flag tells
    the rest of the engine that settled records can no longer be verified.
    """
    if mode == "failure":
        degraded = dict(tables)
        degraded["bank_credits"] = []
        return degraded, False
    return tables, True
