"""
Cheap gates that the project's own tooling can enforce.

Two live NameErrors survived three separate audits — `journals` in
JournalEntry.create_entry (dead CLI journal path, silently swallowed) and
`datetime` in habits.get_consistency_report. Both are found by ruff in under a
second. Nobody had run it, so the suite runs it now.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_lint_correctness_rules_are_clean():
    """ruff's F (pyflakes) and E9 (syntax) families: undefined names, unused
    imports and variables, redefinitions. Not style — these are bugs or the
    residue of one. Style rules are reported in CI but do not gate."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--select", "F,E9", "--quiet"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"correctness lint failures:\n{result.stdout}{result.stderr}"


def test_the_suite_can_run_without_a_funded_api_key():
    """The offline embedding stand-in must actually be installed, otherwise a
    green suite silently depends on a live, billable OpenAI key."""
    import agent.pipeline as pipeline

    vector = pipeline.generate_embedding("a repeatable sentence")
    again = pipeline.generate_embedding("a repeatable sentence")
    assert len(vector) == 1536
    assert vector == again, "the offline embedding must be deterministic"
    assert vector != pipeline.generate_embedding("a different sentence")
