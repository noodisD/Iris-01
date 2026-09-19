"""The documents cannot quietly stop being true.

A glossary that is wrong is worse than none, and this one was: multi-user on
line three, a "decreasing" trajectory no classifier emits, "fading" defined as
something the code does not do, leverage that "causes", a Gemini fallback that
did not exist, and no entry at all for the lifelong or reading engines. The ADR
index stopped at 0013 while 0014 and 0015 were the decisions the month turned
on. Settings offered a hand-kept list of engines that had stopped matching the
one it was validated against.

These fail the build when any of that happens again. They read the code for
what it does rather than keeping a second list of it.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONTEXT = (ROOT / "CONTEXT.md").read_text()


def _returned(func) -> set[str]:
    return set(re.findall(r"return [\"']([a-z][a-z ]*)[\"']", inspect.getsource(func)))


def _quoted_on_lines_mentioning(source: str, word: str) -> set[str]:
    return {q for line in source.splitlines() if word in line
            for q in re.findall(r"[\"']([a-z]+)[\"']", line)}


def _emitted_labels() -> dict[str, set[str]]:
    from agent import decision_impact, lifelong
    from agent.resolution import ResolutionEngine
    from agent.tension import TensionEngine
    from agent.trajectory import TrajectoryEngine

    impact_src = inspect.getsource(decision_impact.DecisionImpactEngine._calculate_impact)
    impact = ({q for line in impact_src.splitlines()
               if re.search(r"\bdirection = |directions\.append\(", line)
               for q in re.findall(r"[\"']([a-z]+)[\"']", line)})
    life_src = inspect.getsource(lifelong)
    life = (_quoted_on_lines_mentioning(life_src, "lifelong_label")
            | _quoted_on_lines_mentioning(life_src, "LIFELONG_CONCENTRATION_SHARE else"))
    return {
        "trajectory": _returned(TrajectoryEngine._classify_trajectory),
        "resolution": _returned(ResolutionEngine._classify_resolution),
        "tension": _returned(TensionEngine._classify_tension),
        "decision impact": impact,
        "lifelong": life - {"lifelong", "label"},
    }


def test_every_label_a_classifier_emits_is_in_the_glossary():
    labels = _emitted_labels()
    assert all(labels.values()), f"a classifier's labels could not be read: {labels}"
    missing = {engine: sorted(l for l in found if f'"{l}"' not in CONTEXT)
               for engine, found in labels.items()}
    assert not any(missing.values()), f"CONTEXT.md does not name: {missing}"


def test_the_glossary_names_no_label_nothing_emits():
    """The inverse drift: "decreasing" sat in the glossary for months."""
    emitted = set().union(*_emitted_labels().values())
    trajectory_section = CONTEXT.split("### Trajectory")[1].split("### ")[0]
    named = set(re.findall(r'"([a-z][a-z ]*)"', trajectory_section))
    assert named <= emitted, f"the glossary names trajectory labels nothing emits: {named - emitted}"


def test_every_adr_is_in_the_index():
    index = (ROOT / "docs" / "adr" / "README.md").read_text()
    missing = [p.name for p in sorted((ROOT / "docs" / "adr").glob("ADR-*.md"))
               if not p.name.startswith("ADR-0000") and p.name not in index]
    assert not missing, f"docs/adr/README.md does not list {missing}"


def test_the_engine_lists_agree():
    """One set of engines, however many places name it."""
    from agent.constants import ENGINE_PRIORITY, SELECTABLE_ENGINES
    from agent.narrative_templates import NARRATIVE_TEMPLATES
    from agent.pipeline_orchestrator import canonical_pipeline

    finding_engines = set(ENGINE_PRIORITY)
    assert set(canonical_pipeline(1).engines) == finding_engines, "what is collected"
    assert set(NARRATIVE_TEMPLATES) == finding_engines, "what can be said"
    assert SELECTABLE_ENGINES == finding_engines | {"observations"}, "what can be switched"

    settings = (ROOT / "frontend" / "src" / "screens" / "SettingsScreen.tsx").read_text()
    block = settings.split("const ENGINE_LABELS")[1].split("};")[0]
    assert set(re.findall(r"^\s+(\w+): '", block, re.M)) == SELECTABLE_ENGINES, "what Settings labels"

    line = next(l for l in CONTEXT.splitlines() if "the selectable engines are" in l)
    named = set(re.findall(r"\b(\w+)(?:,| and|$)", line.split("the selectable engines are")[1]))
    assert named == SELECTABLE_ENGINES, f"what the glossary says: {named}"
