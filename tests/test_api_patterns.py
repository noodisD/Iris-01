"""Invented source-backed discovery, corrections and inspectable comparisons."""

import json
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent import discovery
from agent.database import db
from agent.episodes import EXTRACTION_VERSION
from agent.library import library_hash
from agent.library import load as load_library
from agent.readable import locate
from iris_api import app, get_current_user_id

X = "more-than-can-be-taken-back"
SETBACK = "continuing-after-a-setback"
SETTLED = "settled-in-advance"


def occasion(situation, response, outcome="It went as it went", *, on="2024-05-10",
             modality="happened", entry=1):
    passage = ". ".join(part for part in (situation, response, outcome) if part)
    return {"actor": "self", "modality": modality, "domain": "garden",
            "situation": situation, "demand": None, "information": None,
            "response": response, "outcome": outcome, "explanation": None, "occurredOn": on,
            "citations": [{"entryId": str(entry), "entryDate": on,
                           "sourceType": "reflection", "text": locate(passage, passage)}]}


READING = [
    occasion("The tomatoes failed after the frost", "Replanted the whole bed at once", on="2024-05-01", entry=1),
    occasion("Thinking about next year's beds", "Wrote a planting list", outcome=None,
             modality="planned", on="2024-05-02", entry=2),
    occasion("The seedlings died again", "Bought every tray the shop had", on="2024-05-03", entry=3),
    occasion("A neighbour's plot came free", "Took it on as well", on="2024-05-04", entry=4),
    occasion("Planned the beds in winter", "Planted exactly what was planned", on="2024-05-05", entry=5),
    occasion("Measured the beds before buying", "Chose only the plants that fit", on="2024-05-06", entry=6),
    occasion("Read the soil notes again", "Left room for later changes", on="2024-05-07", entry=7),
]
# Position 1 is the planned account, which is not comparable.
LABELS = {"accounts": 6, "by": {X: "strong-model", SETBACK: "strong-model", SETTLED: "fast-model"},
          "labels": {
              X: {"0": {"tone": "worse", "size": "large"}, "1": {"tone": "worse", "size": "large"},
                  "2": {"tone": "worse", "size": "moderate"}, "3": {"tone": "better", "size": "small"},
                  "4": {"tone": "better", "size": "small"}, "5": {"tone": "better", "size": "small"}},
              SETBACK: {"0": {"tone": "worse", "size": "large"}, "1": {"tone": "worse", "size": "large"},
                        "2": {"tone": "worse", "size": "large"}},
              SETTLED: {"3": {"tone": "better", "size": "small"},
                        "4": {"tone": "better", "size": "small"}, "5": {"tone": "better", "size": "small"}},
          }}


def reading_for(user_id):
    """Invented, source-backed entries through the production journal writer."""
    episodes, revisions = [], {}
    for template in READING:
        source = template["citations"][0]
        entry_id = db.create_reflection(
            user_id, source["text"], reflection_date=date.fromisoformat(template["occurredOn"]))
        revisions[entry_id] = 1
        episodes.append({**template, "citations": [{**source, "entryId": str(entry_id)}]})
    patterns = load_library()
    labels = {**LABELS, "extractionVersion": EXTRACTION_VERSION,
              "libraryHash": library_hash(patterns),
              "labels": {p.id: LABELS["labels"].get(p.id, {}) for p in patterns}}
    return episodes, labels, revisions


def import_reading(user_id, episodes, labels, revisions):
    return discovery.load_reading(
        user_id, episodes, labels, source_revisions=revisions,
        extraction_version=EXTRACTION_VERSION, library_hash=labels["libraryHash"])


def cache_documents(user_id):
    episodes, labels, revisions = reading_for(user_id)
    stamp = "2026-09-29T12:00:00"
    reading = {"version": EXTRACTION_VERSION, "user": user_id,
               "readAt": stamp, "includesStaged": False,
               "sourceRevisions": {str(key): value for key, value in revisions.items()},
               "episodes": episodes}
    return reading, {**labels, "readAt": stamp}, revisions


@pytest.fixture
def reading(test_user):
    return reading_for(test_user["id"])


@pytest.fixture
def loaded(test_user, reading):
    import_reading(test_user["id"], *reading)
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def summary(client, pid):
    return next(p for p in client.get("/api/patterns").json()["patterns"] if p["id"] == pid)


def test_loading_the_same_reading_twice_adds_nothing(test_user, reading):
    first = import_reading(test_user["id"], *reading)
    second = import_reading(test_user["id"], *reading)
    assert first["occasions_added"] == 7 and first["labels_added"] == 12
    assert second.get("occasions_added", 0) == 0 and second.get("labels_added", 0) == 0
    assert second["occasions_already_there"] == 7

def test_labels_are_attached_through_the_list_they_were_made_against(loaded):
    """Position 1 is the dead seedlings, not the planned list in between."""
    shown = [o["situation"] for o in loaded.get(f"/api/patterns/{X}").json()["occasions"]]
    assert "Thinking about next year's beds" not in shown
    assert "The seedlings died again" in shown


def test_labels_made_against_a_different_reading_are_refused(test_user, reading):
    episodes, labels, revisions = reading
    with pytest.raises(ValueError):
        import_reading(test_user["id"], episodes, dict(labels, accounts=9), revisions)


def test_every_library_pattern_is_listed_with_its_counts(loaded):
    patterns = loaded.get("/api/patterns").json()["patterns"]
    assert len(patterns) >= 20
    x = summary(loaded, X)
    assert x["occasions"] == 6
    assert x["tones"] == {"better": 3, "worse": 3, "mixed": 0}
    assert x["labelledBy"] == ["strong-model"]
    assert x["reviewed"] == 0 and x["verdict"] is None
    assert summary(loaded, "switching-cost")["occasions"] == 0


def test_source_backed_sides_and_qualified_denominators(loaded):
    d = loaded.get(f"/api/patterns/{X}").json()
    assert [(row["patternId"], row["better"], row["worse"],
             row["betterTotal"], row["worseTotal"]) for row in d["distinctive"]] == [
        (SETBACK, 0, 3, 3, 3), (SETTLED, 3, 0, 3, 3)]
    assert d["occasions"][0]["citations"][0]["entryId"]


def test_an_occasion_the_owner_rejects_leaves_the_counts_but_stays_visible(loaded):
    d = loaded.get(f"/api/patterns/{X}").json()
    target = next(o for o in d["occasions"] if o["situation"] == "The seedlings died again")
    r = loaded.put(f"/api/patterns/{X}/occasions/{target['id']}", json={"verdict": "no", "note": "a plan, really"})
    assert r.status_code == 200
    assert summary(loaded, X)["occasions"] == 5
    assert summary(loaded, X)["rejected"] == 1
    d = loaded.get(f"/api/patterns/{X}").json()
    assert d["distinctive"] == []  # the smaller side now has only two accounts
    kept = next(o for o in d["occasions"] if o["id"] == target["id"])
    assert kept["ownerVerdict"] == "no" and kept["verdictNote"] == "a plan, really"


def test_reloading_the_reading_never_undoes_a_verdict(loaded, test_user, reading):
    target = loaded.get(f"/api/patterns/{X}").json()["occasions"][0]
    loaded.put(f"/api/patterns/{X}/occasions/{target['id']}", json={"verdict": "yes"})
    import_reading(test_user["id"], *reading)
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


def difference(client, pid, other):
    return next((d for d in client.get("/api/differences").json()["differences"]
                 if d["patternId"] == pid and d["otherId"] == other), None)


def test_insights_include_qualified_fractions_and_exact_group_partition(loaded):
    rows = loaded.get("/api/differences").json()["differences"]
    d = difference(loaded, X, SETBACK)
    assert d in rows
    assert (d["worse"], d["worseTotal"], d["better"], d["betterTotal"]) == (3, 3, 0, 3)
    assert (d["worseRate"], d["betterRate"], d["rateGap"]) == (1.0, 0.0, 1.0)
    response = loaded.get(f"/api/differences/{X}/{SETBACK}")
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert (len(groups["worseWith"]), len(groups["worseWithout"]),
            len(groups["betterWith"]), len(groups["betterWithout"])) == (3, 0, 0, 3)
    assert {citation["entryId"] for group in groups.values() for row in group
            for citation in row["citations"]} == {
                row["citations"][0]["entryId"] for row in loaded.get(f"/api/patterns/{X}").json()["occasions"]}


def test_outcome_pairs_remain_when_conservative_rate_gate_no_longer_qualifies(loaded):
    body = loaded.get("/api/differences").json()
    pair = next(pair for pair in body["reflections"] if pair["patternId"] == X)
    assert pair["better"]["citations"][0]["entryId"] != pair["worse"]["citations"][0]["entryId"]
    assert (pair["betterTotal"], pair["worseTotal"]) == (3, 3)
    better = pair["better"]
    assert loaded.put(f"/api/patterns/{X}/occasions/{better['id']}",
                      json={"verdict": "no"}).status_code == 200
    body = loaded.get("/api/differences").json()
    assert not any(row["patternId"] == X for row in body["differences"])
    assert any(row["patternId"] == X and row["betterTotal"] == 2 for row in body["reflections"])
    loaded.put(f"/api/patterns/{X}/verdict", json={"verdict": "does_not"})
    assert not any(row["patternId"] == X for row in loaded.get("/api/differences").json()["reflections"])


def test_a_pattern_with_only_one_side_compares_nothing(loaded):
    # SETBACK only ever went worse, so there is no better side to set against it.
    assert all(d["patternId"] != SETBACK for d in loaded.get("/api/differences").json()["differences"])


def test_the_owner_judges_an_insight_and_can_change_their_mind(loaded):
    url = f"/api/differences/{X}/{SETBACK}/verdict"
    assert loaded.put(url, json={"verdict": "rings_true"}).status_code == 200
    assert loaded.put(url, json={"verdict": "does_not", "note": "coincidence"}).status_code == 200
    assert difference(loaded, X, SETBACK)["verdict"] == {"verdict": "does_not", "note": "coincidence"}


def test_rejecting_one_side_dissolves_comparison_without_deleting_saved_opinion(loaded):
    loaded.put(f"/api/differences/{X}/{SETBACK}/verdict", json={"verdict": "unsure"})
    better = next(o for o in loaded.get(f"/api/patterns/{X}").json()["occasions"] if o["tone"] == "better")
    loaded.put(f"/api/patterns/{X}/occasions/{better['id']}", json={"verdict": "no"})
    assert difference(loaded, X, SETBACK) is None
    changed = loaded.get(f"/api/differences/{X}/{SETBACK}")
    assert changed.status_code == 409 and changed.json()["detail"] == "This comparison has changed."
    loaded.put(f"/api/patterns/{X}/occasions/{better['id']}", json={"verdict": None})
    assert difference(loaded, X, SETBACK)["verdict"]["verdict"] == "unsure"


def test_unknown_insights_and_verdicts_are_refused(loaded):
    assert loaded.put(f"/api/differences/no-such/{SETBACK}/verdict", json={"verdict": "unsure"}).status_code == 404
    assert loaded.put(f"/api/differences/{X}/{X}/verdict", json={"verdict": "unsure"}).status_code == 404
    assert loaded.put(f"/api/differences/{X}/{SETBACK}/verdict", json={"verdict": "maybe"}).status_code == 422


def test_the_loader_applies_sheet_answers_only_where_none_were_given(tmp_path, monkeypatch, test_user):
    from scripts import load_discovery
    cache, labels, answers = tmp_path / "e.json", tmp_path / "l.json", tmp_path / "a.json"
    reading, labelled, _ = cache_documents(test_user["id"])
    cache.write_text(json.dumps(reading))
    labels.write_text(json.dumps(labelled))
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


def test_the_loader_loads_under_the_same_owner_the_app_shows(tmp_path, monkeypatch):
    """Run with no --user, it must resolve the owner exactly as the app does.

    A first draft asked for a user named "owner", which would have created a
    second user and loaded everything where the app never looks.
    """
    import iris_api
    from agent.database import db
    from scripts import load_discovery
    cache, labels = tmp_path / "e.json", tmp_path / "l.json"
    app_user = db.local_user_id(iris_api.DEFAULT_USERNAME)
    reading, labelled, revisions = cache_documents(app_user)
    cache.write_text(json.dumps(reading))
    labels.write_text(json.dumps(labelled))
    monkeypatch.setattr(sys, "argv", ["load_discovery.py", "--cache", str(cache), "--labels", str(labels),
                                      "--answers", str(tmp_path / "none.json")])
    try:
        assert load_discovery.main() == 0
        assert discovery.occasion_id_for(app_user, reading["episodes"][0]) is not None
    finally:
        for source_id in revisions:
            db.delete_reflection(source_id)


def _row(pid, other, worse, worse_total, better, better_total, verdict=None):
    return {"patternId": pid, "patternName": f"Pattern {pid}", "otherId": other, "otherName": f"Pattern {other}",
            "worse": worse, "worseTotal": worse_total, "better": better, "betterTotal": better_total,
            "verdict": verdict}


def test_a_pair_that_differs_both_ways_is_one_insight_not_two():
    """Each pattern is compared from its own side, so A-with-B and B-with-A
    were listed as two insights: the same finding seen from each end."""
    rows = [_row("a", "b", 7, 13, 1, 4), _row("b", "a", 4, 4, 1, 2), _row("a", "c", 3, 4, 0, 2)]
    kept = discovery.one_per_pair(rows)
    assert sorted((d["patternId"], d["otherId"]) for d in kept) == [("a", "c"), ("b", "a")]


def test_the_direction_the_owner_judged_is_the_one_kept():
    judged = _row("a", "b", 7, 13, 1, 4, verdict={"verdict": "rings_true", "note": None})
    kept = discovery.one_per_pair([_row("b", "a", 4, 4, 1, 2), judged])
    assert kept == [judged]
