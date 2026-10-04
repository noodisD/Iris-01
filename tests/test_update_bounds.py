"""An update stays bounded: few new definitions, asked a few batches at a time."""

from __future__ import annotations

import threading
import time

import pytest

from agent import connections
from agent import discovery_memo as memo
from agent.dynamics import Definition, definition_key


def _definition(n: int) -> Definition:
    return Definition(context_predicate=f"Someone asks me for a favour, case {n}",
                      response_predicate=f"I agree before checking, case {n}",
                      title=f"Case {n}", proposed_account_ids=[], owner_report_ids=[])


class _Draft:
    def __init__(self, definitions, supported):
        self.definitions = definitions
        self.memberships = [type("Row", (), {"dynamic_id": definition_key(d), "role": "support"})()
                            for d in supported]


def test_supported_definitions_keep_their_place_and_few_new_ones_join():
    carried = [_definition(n) for n in range(22)]
    supported = carried[:20]
    new = [_definition(100 + n) for n in range(15)]
    merged = new[:3] + carried + new[3:]  # some new ones outrank the carried
    chosen = connections._admit(merged, _Draft(carried, supported))
    keys = {definition_key(d) for d in chosen}
    assert all(definition_key(d) in keys for d in supported), "supported definitions stay"
    assert sum(definition_key(d) in {definition_key(n) for n in new} for d in chosen) == \
        connections.MAX_NEW_DEFINITIONS
    assert len(chosen) == 25, "past the cap only by the new ones"
    assert [d for d in merged if definition_key(d) in keys] == chosen, "rank order kept"


def test_unsupported_carried_definitions_fill_the_room_left():
    carried = [_definition(n) for n in range(10)]
    chosen = connections._admit(carried + [_definition(100)], _Draft(carried, carried[:4]))
    assert len(chosen) == 11


def test_batches_run_together_in_the_callers_memo_scope_and_keep_their_order():
    running, peak, lock = [0], [0], threading.Lock()

    def decide(batch):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return batch, memo.active()

    with memo.remembering(1):
        results = connections._in_parallel(list(range(12)), decide)
    assert [batch for batch, _ in results] == list(range(12))
    assert all(active for _, active in results), "the memo scope follows each batch"
    assert peak[0] > 1


def test_every_batch_finishes_before_a_failure_is_raised():
    done = []

    def decide(batch):
        if batch == 0:
            raise ValueError("bad reply")
        time.sleep(0.02)
        done.append(batch)

    with pytest.raises(ValueError):
        connections._in_parallel(list(range(8)), decide)
    assert sorted(done) == list(range(1, 8))
