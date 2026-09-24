"""Discovery in the app: occasions, the library patterns they belong to, and verdicts.

Loads an invented reading through the same path the real one takes, then
asserts what the Patterns screen is shown: counts by how occasions went, the
two sides and what else was true on each, and that the owner's verdicts change
the counts without deleting anything. Every occasion here is invented.
"""

import json
import sys

import pytest
from fastapi.testclient import TestClient

from agent import discovery
from agent.library import load as load_library
from iris_api import app, get_current_user_id

X = "more-than-can-be-taken-back"
SETBACK = "continuing-after-a-setback"
SETTLED = "settled-in-advance"


def occasion(situation, response, outcome="It went as it went.", *, on="2024-05-10",
             modality="happened", entry=1):
    return {"actor": "self", "modality": modality, "domain": "garden",
            "situation": situation, "demand": None, "information": None,
            "response": response, "outcome": outcome, "explanation": None, "occurredOn": on,
            "citations": [{"entryId": str(entry), "entryDate": on,
                           "sourceType": "reflection", "text": situation}]}


READING = [
    occasion("The tomatoes failed after the frost", "Replanted the whole bed at once", on="2024-05-01", entry=1),
    occasion("Thinking about next year's beds", "Wrote a planting list", outcome=None,
             modality="planned", on="2024-05-02", entry=2),
    occasion("The seedlings died again", "Bought every tray the shop had", on="2024-05-03", entry=3),
    occasion("A neighbour's plot came free", "Took it on as well", on="2024-05-04", entry=4),
    occasion("Planned the beds in winter", "Planted exactly what was planned", on="2024-05-05", entry=5),
]
# Keyed by position among the comparable occasions: the planned one is not
# comparable, so 0, 1, 2, 3 are READING[0], [2], [3], [4].
LABELS = {"accounts": 4, "by": {X: "strong-model", SETBACK: "strong-model", SETTLED: "fast-model"},
          "labels": {
              X: {"0": {"tone": "worse", "size": "large"}, "1": {"tone": "worse", "size": "large"},
                  "2": {"tone": "worse", "size": "moderate"}, "3": {"tone": "better", "size": "small"}},
              SETBACK: {"0": {"tone": "worse", "size": "large"}, "1": {"tone": "worse", "size": "large"},
                        "2": {"tone": "worse", "size": "large"}},
              SETTLED: {"3": {"tone": "better", "size": "small"}},
          }}


@pytest.fixture
def loaded(test_user):
    discovery.load_reading(test_user["id"], READING, LABELS)
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def summary(client, pid):
    return next(p for p in client.get("/api/patterns").json()["patterns"] if p["id"] == pid)


def test_loading_the_same_reading_twice_adds_nothing(test_user):
    first = discovery.load_reading(test_user["id"], READING, LABELS)
    second = discovery.load_reading(test_user["id"], READING, LABELS)
    assert first["occasions_added"] == 5 and first["labels_added"] == 8
    assert second.get("occasions_added", 0) == 0 and second.get("labels_added", 0) == 0
    assert second["occasions_already_there"] == 5


def test_labels_are_attached_through_the_list_they_were_made_against(loaded):
    """Position 1 is the dead seedlings, not the planned list in between."""
    shown = [o["situation"] for o in loaded.get(f"/api/patterns/{X}").json()["occasions"]]
    assert "Thinking about next year's beds" not in shown
    assert "The seedlings died again" in shown


def test_labels_made_against_a_different_reading_are_refused(test_user):
    with pytest.raises(ValueError):
        discovery.load_reading(test_user["id"], READING, dict(LABELS, accounts=9))


def test_every_library_pattern_is_listed_with_its_counts(loaded):
    patterns = loaded.get("/api/patterns").json()["patterns"]
    assert len(patterns) >= 20
    x = summary(loaded, X)
    assert x["occasions"] == 4
    assert x["tones"] == {"better": 1, "worse": 3, "mixed": 0}
    assert x["labelledBy"] == ["strong-model"]
    assert x["reviewed"] == 0 and x["verdict"] is None
    assert summary(loaded, "switching-cost")["occasions"] == 0


def test_the_two_sides_and_what_else_was_true_on_each(loaded):
    d = loaded.get(f"/api/patterns/{X}").json()
    assert d["alsoTrue"]["worse"] == {SETBACK: 3}
    assert d["alsoTrue"]["better"] == {SETTLED: 1}
    # A difference of one is two occasions and a coincidence; three is shown.
    assert [(x["patternId"], x["better"], x["worse"]) for x in d["distinctive"]] == [(SETBACK, 0, 3)]
    assert d["occasions"][0]["citations"][0]["entryId"]  # links back to the journal entry


def test_an_occasion_the_owner_rejects_leaves_the_counts_but_stays_visible(loaded):
    d = loaded.get(f"/api/patterns/{X}").json()
    target = next(o for o in d["occasions"] if o["situation"] == "The seedlings died again")
    r = loaded.put(f"/api/patterns/{X}/occasions/{target['id']}", json={"verdict": "no", "note": "a plan, really"})
    assert r.status_code == 200
    assert summary(loaded, X)["occasions"] == 3
    assert summary(loaded, X)["rejected"] == 1
    d = loaded.get(f"/api/patterns/{X}").json()
    assert d["alsoTrue"]["worse"] == {SETBACK: 2}
    kept = next(o for o in d["occasions"] if o["id"] == target["id"])
    assert kept["ownerVerdict"] == "no" and kept["verdictNote"] == "a plan, really"


def test_reloading_the_reading_never_undoes_a_verdict(loaded, test_user):
    target = loaded.get(f"/api/patterns/{X}").json()["occasions"][0]
    loaded.put(f"/api/patterns/{X}/occasions/{target['id']}", json={"verdict": "yes"})
    discovery.load_reading(test_user["id"], READING, LABELS)
    again = next(o for o in loaded.get(f"/api/patterns/{X}").json()["occasions"] if o["id"] == target["id"])
    assert again["ownerVerdict"] == "yes"


def test_a_verdict_on_an_occasion_the_pattern_does_not_label_is_a_404(loaded):
    other = loaded.get(f"/api/patterns/{SETTLED}").json()["occasions"][0]
    assert loaded.put(f"/api/patterns/switching-cost/occasions/{other['id']}",
                      json={"verdict": "yes"}).status_code == 404


def test_the_owner_can_say_whether_a_pattern_rings_true_and_change_their_mind(loaded):
    assert loaded.put(f"/api/patterns/{X}/verdict", json={"verdict": "rings_true"}).status_code == 200
    assert loaded.put(f"/api/patterns/{X}/verdict",
                      json={"verdict": "does_not", "note": "not quite"}).status_code == 200
    assert summary(loaded, X)["verdict"] == {"verdict": "does_not", "note": "not quite"}


def test_unknown_patterns_and_verdicts_are_refused(loaded):
    assert loaded.get("/api/patterns/no-such-pattern").status_code == 404
    assert loaded.put("/api/patterns/no-such-pattern/verdict", json={"verdict": "unsure"}).status_code == 404
    assert loaded.put(f"/api/patterns/{X}/verdict", json={"verdict": "maybe"}).status_code == 422


def test_the_loader_applies_sheet_answers_only_where_none_were_given(tmp_path, monkeypatch, test_user):
    from scripts import load_discovery
    cache, labels, answers = tmp_path / "e.json", tmp_path / "l.json", tmp_path / "a.json"
    cache.write_text(json.dumps({"episodes": READING}))
    labels.write_text(json.dumps(LABELS))
    answers.write_text(json.dumps({"pattern": X, "occasions": {
        "k0": {"index": 0, "is_it": "yes", "note": "from the sheet"},
        "k1": {"index": 3, "is_it": "no", "note": None}}}))
    argv = ["load_discovery.py", "--user", str(test_user["id"]), "--cache", str(cache),
            "--labels", str(labels), "--answers", str(answers)]
    monkeypatch.setattr(sys, "argv", argv)
    assert load_discovery.main() == 0
    d = discovery.detail(test_user["id"], next(p for p in load_library() if p.id == X))
    verdicts = {o["situation"]: o["label"]["owner_verdict"] for o in d["occasions"]}
    assert verdicts["The tomatoes failed after the frost"] == "yes"
    assert verdicts["A neighbour's plot came free"] == "no"
    # A second run changes nothing it has already set.
    assert load_discovery.main() == 0
