"""Editorial lenses have explicit process requirements and bounded provenance."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from agent.library import LIBRARY_PATH, Lens, library_hash, load


def _catalogue(tmp_path, mutate):
    document = json.loads(LIBRARY_PATH.read_text())
    mutate(document)
    path = tmp_path / "library.json"
    path.write_text(json.dumps(document))
    return path


def test_library_loads_with_two_requirements_and_source_scopes():
    lenses = load()
    assert len(lenses) == 24
    assert all(isinstance(lens, Lens) and len(lens.requires) == 2 for lens in lenses)
    assert len({lens.id for lens in lenses}) == len(lenses)
    assert {lens.family for lens in lenses} == {
        "belonging", "uncertainty", "self_worth", "emotional_protection", "capacity", "agency"
    }
    assert all(lens.sources and all("personal match" in source.scope for source in lens.sources)
               for lens in lenses)
    with pytest.raises(FrozenInstanceError):
        lenses[0].name = "a personal verdict"


@pytest.mark.parametrize("mutate", [
    lambda doc: doc.update(version=3),
    lambda doc: doc["lenses"].append(doc["lenses"][0]),
    lambda doc: doc["lenses"][0].update(extra="unsupported"),
    lambda doc: doc["lenses"][0].update(family="diagnosis"),
    lambda doc: doc["lenses"][0].update(requires=["behaviour only"]),
    lambda doc: doc["lenses"][0].update(sourceIds=["missing"]),
    lambda doc: doc["lenses"][0].update(question="This is your problem."),
    lambda doc: doc["sources"]["case_formulation"].update(kind="proof"),
])
def test_invalid_catalogue_fails_whole_load(tmp_path, mutate):
    with pytest.raises(ValueError):
        load(_catalogue(tmp_path, mutate))


def test_hash_changes_for_requirements_and_bibliographic_scope(tmp_path):
    original = library_hash(load())
    assert original == library_hash(load())
    changed_requirement = _catalogue(tmp_path, lambda doc: doc["lenses"][0]["requires"].__setitem__(
        0, "Agreement happens before asking about availability"))
    assert library_hash(load(changed_requirement)) != original
    changed_source = _catalogue(tmp_path, lambda doc: doc["sources"]["case_formulation"].update(
        scope="This source is only a hypothetical framework, never proof of a personal match."))
    assert library_hash(load(changed_source)) != original
