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


#: The ruff families that gate — the same selection CI runs. F (pyflakes) and E9
#: (syntax) are bugs or their residue; the rest were already clean and are held
#: there. The full ruleset used to run in CI as `|| true`: a red light painted
#: green, which only teaches people to stop looking at lights. What gates is what
#: can fail; a family joins when it is clean.
GATING_RULES = "F,E9,UP,C4,PIE,PGH,PYI,EXE"


def test_the_gating_lint_rules_are_clean():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--select", GATING_RULES, "--quiet"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"lint failures:\n{result.stdout}{result.stderr}"


def test_ci_gates_on_the_same_rules():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert f"--select {GATING_RULES}" in ci
    assert "|| true" not in ci, "an advisory step that can never fail is not a check"


def test_the_typed_modules_pass_mypy():
    """The allow-list in pyproject.toml, checked strictly. A typechecker that
    was configured and never run was a sticker."""
    result = subprocess.run([sys.executable, "-m", "mypy"], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, f"mypy:\n{result.stdout}{result.stderr}"


def test_the_suite_can_run_without_a_funded_api_key():
    """The offline embedding stand-in must actually be installed, otherwise a
    green suite silently depends on a live, billable OpenAI key."""
    import agent.pipeline as pipeline

    vector = pipeline.generate_embedding("a repeatable sentence")
    again = pipeline.generate_embedding("a repeatable sentence")
    assert len(vector) == 1536
    assert vector == again, "the offline embedding must be deterministic"
    assert vector != pipeline.generate_embedding("a different sentence")


def test_no_route_handler_blocks_the_event_loop():
    """A handler declared `async def` runs on the event loop. Almost every
    handler here does blocking work — database queries, embedding calls, the
    engines — so declaring it async stalls every other request, including the
    chat stream, for its duration. Handlers must be `def` unless they genuinely
    await, in which case FastAPI gives them a threadpool instead."""
    import ast

    tree = ast.parse((ROOT / "iris_api.py").read_text())
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        routes = [
            d for d in node.decorator_list
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and isinstance(d.func.value, ast.Name) and d.func.value.id == "app"
        ]
        if not routes:
            continue
        awaits = any(
            isinstance(n, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for n in ast.walk(node)
        )
        if not awaits:
            offenders.append(f"{node.name} ({routes[0].args[0].value})")

    assert not offenders, (
        "these handlers are async but never await, so their blocking work runs "
        "on the event loop:\n  " + "\n  ".join(offenders)
    )
