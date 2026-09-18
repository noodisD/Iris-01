"""The package must import. All of it, in any order.

This exists because it did not. `agent.pipeline` imported `agent.constructs` at
module scope so that a new entry could be classified against confirmed
constructs, and `agent.constructs` imported `generate_embedding` back from
`agent.pipeline` at module scope. Since `agent.work_queue` imports `pipeline`,
and `agent/__init__` reaches it through `core` → `journal_entry` → `trackers`,
the cycle made *every* import in the package fail.

Nothing caught it. The test suite did not fail on an assertion — conftest itself
could not load, so the entire run collapsed before a single test was collected,
which reads as an environment problem rather than a code defect.

It is the second time a module-scope import in `constructs.py` has caused this:
`Intelligence` was made lazy for the same reason, which is why `discover()`
imports it inside the function. A cheap structural test is worth more than
remembering the convention.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

#: Every module that sits on an import path something else depends on. Ordered
#: deliberately: each is also used as a *first* import below, because a cycle
#: often only appears when a particular module is the one that starts the chain.
CORE_MODULES = [
    "agent",
    "agent.pipeline",
    "agent.constructs",
    "agent.observations",
    "agent.work_queue",
    "agent.persistence",
    "agent.core",
    "agent.insights_service",
    "agent.comparison",
    "agent.database",
]


@pytest.mark.parametrize("module", CORE_MODULES)
def test_each_module_imports_on_its_own(module):
    """In a fresh interpreter, so import order is this module's alone.

    Importing inside the running process proves little: pytest has already
    imported most of the package through conftest, so a cycle would be hidden by
    modules that happen to be in sys.modules already.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, (
        f"importing {module} first fails:\n{result.stderr[-1500:]}"
    )


def test_the_two_modules_that_reference_each_other_both_load():
    """pipeline classifies against constructs; constructs embeds through
    pipeline. Whichever arrives first, both must finish initialising."""
    for first, second in (("agent.pipeline", "agent.constructs"),
                          ("agent.constructs", "agent.pipeline")):
        result = subprocess.run(
            [sys.executable, "-c", f"import {first}, {second}"],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, (
            f"{first} then {second} fails:\n{result.stderr[-1500:]}"
        )


def test_constructs_does_not_bind_the_pipeline_at_module_scope():
    """The specific shape of the break, named so it cannot come back quietly.

    `generate_embedding` is imported inside `promote()`. If it reappears at
    module scope the package stops importing, and the failure will look like a
    broken environment rather than a broken import.
    """
    constructs = importlib.import_module("agent.constructs")
    assert not hasattr(constructs, "generate_embedding"), (
        "constructs binds pipeline at module scope again; the cycle is back"
    )
