"""Regression tests for the analytical-integrity defects found in the pipeline audit.

Each test here encodes a counterexample that the code used to produce. They are
deliberately DB-free: they exercise the real methods with the external boundary
(database, embedding provider) mocked, so they run in any environment and fail
for one reason only.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from agent.constants import (
    PERSISTENCE_CLUSTER_THRESHOLD,
)
from agent.persistence import PersistenceEngine


# --- discovery must not invent themes ---------------------------------------


def _unit_rows(vectors, source_type="journal_entry"):
    """Shape vectors like get_unassigned_embeddings() returns them."""
    base = datetime(2026, 9, 1, tzinfo=UTC)
    return [
        {
            "vector": v.tolist(),
            "source_type": source_type,
            "source_id": 100 + i,
            # embedded now, but the entry itself is a year old
            "created_at": base + timedelta(days=i),
            "occurred_at": base - timedelta(days=365 - i),
        }
        for i, v in enumerate(vectors)
    ]


def _at_cosine(anchor: np.ndarray, cos: float, rng) -> np.ndarray:
    """A unit vector whose cosine to `anchor` is exactly `cos`.

    Adding scaled gaussian noise does not work in 1536 dimensions: the noise
    norm grows as sqrt(d), so any visible scale swamps the anchor and the
    "coherent" fixture is really a random one.
    """
    perp = rng.normal(size=anchor.shape).astype(np.float32)
    perp -= anchor * float(perp @ anchor)
    perp /= np.linalg.norm(perp)
    v = cos * anchor + float(np.sqrt(1.0 - cos * cos)) * perp
    return (v / np.linalg.norm(v)).astype(np.float32)


def _discover(rows):
    """Run the real discover_themes with only the DB boundary replaced."""
    engine = PersistenceEngine(user_id=1)
    created = []
    with patch("agent.persistence.embeddings") as emb:
        emb.get_unassigned_embeddings.return_value = rows
        with patch.object(
            engine, "_create_theme_from_cluster",
            side_effect=lambda vecs, entries: created.append(entries) or {"id": len(created)},
        ):
            engine.discover_themes()
    return created


def test_unrelated_entries_do_not_become_a_theme():
    """Five mutually unrelated vectors used to form one size-five theme.

    eps was max(cosine-distance floor, mean k-th neighbour distance). In 1536
    dimensions that second term is ~1.41 — the distance between orthogonal unit
    vectors — so it always won and the semantic cutoff never applied.
    """
    rng = np.random.default_rng(7)
    v = rng.normal(size=(5, 1536)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)

    cos = v @ v.T
    np.fill_diagonal(cos, -1.0)
    assert cos.max() < 0.2, "fixture must actually be unrelated"

    assert _discover(_unit_rows(v)) == [], (
        f"unrelated entries (max pairwise cosine {cos.max():.3f}) formed a theme"
    )


def test_a_coherent_cluster_is_still_discovered():
    """The negative control must not have been bought by rejecting everything."""
    rng = np.random.default_rng(11)
    anchor = rng.normal(size=1536).astype(np.float32)
    anchor /= np.linalg.norm(anchor)

    # Tightly related entries: paraphrases of one another.
    vectors = np.array([_at_cosine(anchor, 0.95, rng) for _ in range(5)])
    assert (vectors @ vectors.T).min() > PERSISTENCE_CLUSTER_THRESHOLD

    created = _discover(_unit_rows(vectors))
    assert len(created) == 1, "a genuinely coherent cluster must still form a theme"
    assert len(created[0]) == 5


def test_cohesion_rejects_a_chained_cluster():
    """Density clustering chains: A~B~C with A and C unrelated is not a theme."""
    engine = PersistenceEngine(user_id=1)
    rng = np.random.default_rng(3)
    a = rng.normal(size=1536).astype(np.float32)
    a /= np.linalg.norm(a)
    b = _at_cosine(a, 0.05, rng)
    middle = (a + b) / np.linalg.norm(a + b)

    chain = np.array([a, middle, b])
    assert float(a @ b) < 0.2, "the ends of the chain must be unrelated"
    assert not engine._is_cohesive(chain), (
        "A~B~C with A and C unrelated is a chain, not one pattern"
    )


def test_cohesion_requires_every_member_to_match_its_own_centroid():
    engine = PersistenceEngine(user_id=1)
    rng = np.random.default_rng(5)
    anchor = rng.normal(size=1536).astype(np.float32)
    anchor /= np.linalg.norm(anchor)

    tight = [_at_cosine(anchor, 0.93, rng) for _ in range(4)]
    assert engine._is_cohesive(np.array(tight))

    stranger = _at_cosine(anchor, 0.10, rng)
    assert not engine._is_cohesive(np.array(tight + [stranger])), (
        "one member that would not clear the creation threshold must block it"
    )


def test_eps_uses_the_euclidean_distance_for_the_cosine_threshold():
    """The metric is euclidean over normalized vectors, so |a-b| = sqrt(2(1-cos))."""
    import inspect

    src = inspect.getsource(PersistenceEngine.discover_themes)
    assert "np.sqrt(2.0 * (1.0 - PERSISTENCE_CLUSTER_THRESHOLD))" in src
    assert "avg_kth_distance" not in src, (
        "eps must bound the data, not adapt to it"
    )


# --- evidence bundles belong to one theme each ------------------------------


def test_each_theme_gets_only_its_own_evidence():
    """The buffer was created once per engine and only appended to, so a run
    over several themes filed theme 1's metrics inside theme 2's bundle."""
    engine = PersistenceEngine(user_id=1)
    now = datetime.now(UTC)

    themes_rows = [
        {"id": 1, "summary": "One", "occurrence_count": 5, "user_id": 1},
        {"id": 2, "summary": "Two", "occurrence_count": 9, "user_id": 1},
    ]
    occ = {
        1: [{"occurred_at": now - timedelta(days=d), "source_type": "journal_entry"}
            for d in range(5)],
        2: [{"occurred_at": now - timedelta(days=d), "source_type": "journal_entry"}
            for d in range(9)],
    }

    recorded = {}
    with patch("agent.persistence.themes") as th, \
         patch("agent.persistence.confidence_repo") as conf_repo, \
         patch.object(engine, "ev_engine") as ev:
        th.get_all_themes.return_value = themes_rows
        th.get_occurrences.side_effect = lambda tid: occ[tid]
        conf_repo.get_confidence.return_value = None
        ev.record_evidence.side_effect = (
            lambda engine_name, ptype, pid, bundle, **kw: recorded.__setitem__(
                pid, [e["key"] for e in bundle]
            )
        )
        engine.get_persistent_themes()

    assert set(recorded) == {1, 2}, f"both themes must file a bundle: {recorded}"
    for theme_id, keys in recorded.items():
        assert len(keys) == len(set(keys)), (
            f"theme {theme_id}'s bundle contains another theme's metrics: {keys}"
        )


# --- provenance: a snippet must come from its own table ---------------------


def test_discovery_reads_the_snippet_from_the_source_type_it_was_given():
    """Without the source type this defaulted to journal_entry, so a reflection
    quoted whatever journal row shared its numeric id."""
    engine = PersistenceEngine(user_id=1)
    looked_up = []

    with patch("agent.persistence.embeddings") as emb, \
         patch("agent.persistence.themes") as th, \
         patch.object(engine, "_generate_theme_summary", return_value="A theme"):
        emb.get_content_for_source.side_effect = (
            lambda stype, sid: looked_up.append((stype, sid)) or "text"
        )
        th.create_theme.return_value = 42

        vectors = np.ones((2, 1536), dtype=np.float32)
        entries = [
            {"source_type": "reflection", "source_id": 7,
             "occurred_at": datetime(2026, 9, 1, tzinfo=UTC)},
            {"source_type": "habit_completion", "source_id": 8,
             "occurred_at": datetime(2026, 9, 2, tzinfo=UTC)},
        ]
        engine._create_theme_from_cluster(vectors, entries)

    assert ("reflection", 7) in looked_up, f"looked up {looked_up}"
    assert ("habit_completion", 8) in looked_up, f"looked up {looked_up}"
    assert not any(t == "journal_entry" for t, _ in looked_up), (
        f"a non-journal source was read from the journal table: {looked_up}"
    )


# --- presentation must not invent numbers -----------------------------------


def _service_over(engine_results: dict):
    """An InsightsService whose engines return exactly these results."""
    from agent import insights_service as mod

    service = mod.InsightsService(user_id=1)
    patches = []
    for name, cls in [
        ("trajectory", "TrajectoryEngine"), ("resolution", "ResolutionEngine"),
        ("tension", "TensionEngine"), ("leverage", "LeverageEngine"),
        ("decision_impact", "DecisionImpactEngine"),
    ]:
        instance = MagicMock()
        results = engine_results.get(name, [])
        instance.analyze_all_themes.return_value = results
        instance.analyze_all_tensions.return_value = results
        instance.analyze_all_leverage.return_value = results
        instance.analyze_all_anchors.return_value = results
        patches.append(patch.object(mod, cls, return_value=instance))
    for p in patches:
        p.start()
    try:
        return service, service._normalize()
    finally:
        for p in patches:
            p.stop()


def test_tension_keeps_its_own_recent_and_earlier_split():
    """A tension with four recent and eight earlier shared days was rendered as
    "12 recent · 0 earlier": the all-time total moved into the recent slot and
    the earlier count was invented as zero."""
    service, raw = _service_over({"tension": [{
        "theme_a_id": 1, "theme_b_id": 2,
        "theme_a_summary": "Late nights", "theme_b_summary": "Low energy",
        "cooccurrence_count": 12,
        "recent_cooccurrence_count": 4,
        "past_cooccurrence_count": 8,
        "tension_label": "persistent", "confidence_level": "high",
    }]})

    assert len(raw) == 1
    values = {m["label"]: m["value"] for m in raw[0]["measures"]}
    assert values["Recent"] == 4, values
    assert values["Earlier"] == 8, values
    assert values["All time"] == 12, values

    summary = service._summary(raw[0], 0, None, "2026-09-10T00:00:00Z")
    assert "4 shared days" in summary["headline"]["line3"]
    assert "0 earlier" not in summary["summary"], summary["summary"]
    assert "12 recent" not in summary["summary"], summary["summary"]


def test_leverage_does_not_claim_a_recent_versus_earlier_comparison():
    """Leverage measures association within a lag window. It has no earlier
    window, so it must not report one — least of all a fabricated zero."""
    service, raw = _service_over({"leverage": [{
        "source_id": 1, "target_id": 2,
        "source_summary": "Running", "target_summary": "Good sleep",
        "influence_score": 0.42, "directional_lift": 0.8,
        "cooccurrence_count": 9, "confidence_level": "medium",
    }]})

    labels = {m["label"] for m in raw[0]["measures"]}
    assert "Earlier" not in labels, labels
    assert "Co-occurrences" in labels

    detail_evidence = service._evidence(raw[0])
    comparison = next(e for e in detail_evidence if e["kind"] == "comparison")
    assert all(i["value"] != 0 or i["label"] != "Earlier" for i in comparison["items"])
    assert comparison["label"] == "Temporal association"


def test_decision_impact_reports_relative_change_not_all_history_as_recent():
    """target_total_count is every occurrence the target ever had. It was being
    shown as a recent count against an invented earlier zero."""
    service, raw = _service_over({"decision_impact": [{
        "anchor_id": 1, "target_id": 2,
        "anchor_summary": "Started therapy", "target_summary": "Rumination",
        "effect_direction": "decrease", "delta_score": -0.4,
        "consistency_ratio": 0.75, "target_total_count": 40,
        "confidence_level": "medium",
    }]})

    values = {m["label"]: m["value"] for m in raw[0]["measures"]}
    assert values["Relative change in rate"] == -0.4
    assert values["Target occurrences"] == 40

    total = next(m for m in raw[0]["measures"] if m["label"] == "Target occurrences")
    assert total["sub"] == "all time", "an all-history count must say so"

    summary = service._summary(raw[0], 0, None, "2026-09-10T00:00:00Z")
    assert "40 recent" not in summary["summary"], summary["summary"]
    assert "-40%" in summary["headline"]["line3"], summary["headline"]["line3"]


def test_no_engine_is_presented_as_causal():
    """No engine performs causal identification, so none may be labelled that
    way on screen."""
    from agent.insights_service import KIND_MAP

    assert "causal" not in KIND_MAP.values(), KIND_MAP


def test_confidence_label_reaches_the_screen():
    """The numeric field is an ordinal encoding, not a probability. The real
    label has to be visible somewhere."""
    service, raw = _service_over({"trajectory": [{
        "theme_id": 1, "theme_summary": "Focus", "trajectory_label": "increasing",
        "recent_count": 6, "past_count": 2, "confidence_level": "medium",
    }]})
    summary = service._summary(raw[0], 0, None, "2026-09-10T00:00:00Z")
    assert "medium confidence" in summary["tags"], summary["tags"]


# --- a failed analysis is not a completed one -------------------------------


def test_persistence_failure_does_not_mark_the_source_complete():
    """The exception was caught and the row was then marked 'complete', so the
    queue deleted the task. The embedding existed and the occurrence never did."""
    from agent import pipeline

    statuses = []
    with patch.object(pipeline, "embeddings") as emb, \
         patch.object(pipeline, "generate_embedding", return_value=[0.1] * 1536), \
         patch.object(pipeline, "PersistenceEngine") as pe:
        emb.update_processing_status.side_effect = (
            lambda stype, sid, status: statuses.append(status)
        )
        emb.get_items_to_process.return_value = [{
            "id": 5, "content": "text", "user_id": 1,
            "occurred_at": datetime(2026, 9, 1, tzinfo=UTC),
        }]
        pe.return_value.check_persistence.side_effect = RuntimeError("engine down")

        with pytest.raises(RuntimeError):
            pipeline.run_processing_pipeline("journal_entry", 5)

    assert "complete" not in statuses, (
        f"a failed analysis was acknowledged as success: {statuses}"
    )
    assert statuses[-1] == "failed", statuses


def test_the_queue_retries_a_failed_analysis_instead_of_deleting_it():
    from agent import work_queue

    deleted, failed = [], []
    with patch.object(work_queue, "_claim_due", return_value=[{
            "id": 900, "user_id": 1, "source_type": "journal_entry",
            "source_id": 5, "attempts": 1}]), \
         patch.object(work_queue, "run_processing_pipeline",
                      side_effect=RuntimeError("engine down")), \
         patch.object(work_queue, "_succeed", side_effect=lambda i: deleted.append(i)), \
         patch.object(work_queue, "_fail",
                      side_effect=lambda i, a, e: failed.append(i)):
        succeeded, failures = work_queue.process_due()

    assert (succeeded, failures) == (0, 1), (succeeded, failures)
    assert deleted == [], "the task must survive to be retried"
    assert failed == [900]


# --- eligibility is one rule, not two ---------------------------------------


def test_discovery_and_the_online_path_admit_the_same_sources():
    """Discovery admitted `habit` — the habit *definition*, an intention rather
    than behaviour — while the online path never did. A habit someone created
    and never performed could found a theme and count as an occurrence of it.
    ADR-0003: evidence is what the user deliberately logged.
    """
    import inspect

    from agent.database import Database
    from agent.pipeline import run_processing_pipeline

    sql = inspect.getsource(Database.get_unassigned_embeddings)
    online = inspect.getsource(run_processing_pipeline)

    assert "e.source_type = 'habit'" not in sql, (
        "habit definitions are not evidence"
    )
    for source in ("journal_entry", "reflection", "habit_completion"):
        assert source in sql, f"{source} must stay eligible for discovery"
        assert source in online, f"{source} must stay eligible online"


def test_the_offline_embedding_fixture_is_semantically_meaningful():
    """The suite's stand-in embedder hashed the whole string, so two nearly
    identical sentences were as unrelated as any two in the language. Themes
    formed in integration tests only because discovery's eps had grown to the
    distance between orthogonal vectors — the suite asserted on the bug.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_conftest_probe", "tests/conftest.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # pragma: no cover - needs the test database env
        pytest.skip("conftest requires the test database environment")

    near = np.array([module._offline_embedding(f"Poor Sleep again {i}") for i in range(5)])
    far = np.array(module._offline_embedding("Deep focus at work today"))

    pairwise = near @ near.T
    off_diagonal = pairwise[~np.eye(len(near), dtype=bool)]

    assert off_diagonal.min() > PERSISTENCE_CLUSTER_THRESHOLD, (
        f"entries saying the same thing must land near each other, "
        f"got {off_diagonal.min():.3f}"
    )
    assert abs(float(near[0] @ far)) < 0.3, "unrelated entries must stay apart"


# --- a theme is dated by when its entries happened --------------------------


def test_a_discovered_theme_is_dated_by_the_event_not_the_embedding():
    """Discovery dated themes and occurrences by embeddings.created_at, so an
    entry backdated to March — or one embedded late after a provider outage —
    was recorded as having happened when the queue got to it. The matching path
    always used the source's own date, so the same entry landed on a different
    date depending on whether it founded a theme or joined one."""
    engine = PersistenceEngine(user_id=1)

    embedded_at = datetime(2026, 9, 10, tzinfo=UTC)
    happened_at = datetime(2026, 3, 4, tzinfo=UTC)

    created = {}
    occurrences = []
    with patch("agent.persistence.embeddings") as emb, \
         patch("agent.persistence.themes") as th, \
         patch.object(engine, "_generate_theme_summary", return_value="A theme"):
        emb.get_content_for_source.return_value = "text"
        th.create_theme.side_effect = lambda **kw: created.update(kw) or 42
        th.add_occurrence.side_effect = lambda **kw: occurrences.append(kw)

        vectors = np.ones((2, 1536), dtype=np.float32)
        entries = [
            {"source_type": "journal_entry", "source_id": 1,
             "created_at": embedded_at, "occurred_at": happened_at},
            {"source_type": "journal_entry", "source_id": 2,
             "created_at": embedded_at, "occurred_at": happened_at + timedelta(days=1)},
        ]
        engine._create_theme_from_cluster(vectors, entries)

    assert created["first_seen_at"].startswith("2026-03-04"), created["first_seen_at"]
    assert created["last_seen_at"].startswith("2026-03-05"), created["last_seen_at"]
    for occ in occurrences:
        assert occ["occurred_at"].startswith("2026-03-0"), occ["occurred_at"]


def test_discovery_asks_the_database_for_the_event_time():
    """The repository has to supply it, or the engine falls back to embedding time."""
    import inspect

    from agent.database import Database

    sql = inspect.getsource(Database.get_unassigned_embeddings)
    assert "AS occurred_at" in sql
    assert "r.reflection_date" in sql, "a reflection happened on its reflection_date"
    assert "hc.completion_date" in sql, "a completion happened on its completion_date"


# --- replaying a source must not inflate the evidence -----------------------


def test_theme_stats_are_derived_from_occurrences_not_incremented():
    """add_theme_occurrence is an upsert, but the stats update was an
    unconditional `occurrence_count + 1`, so a queue retry or replay wrote one
    occurrence and counted it twice. The overwrite of last_seen_at also moved it
    *backwards* whenever a historical entry was backfilled."""
    import inspect

    from agent.database import Database

    sql = inspect.getsource(Database.update_theme_stats)
    assert "occurrence_count + 1" not in sql, (
        "an upserted occurrence must not increment a counter"
    )
    assert "COUNT(*)" in sql and "FROM theme_occurrences" in sql, (
        "the count has to come from the occurrences that exist"
    )
    assert "MAX(occurred_at)" in sql, "last_seen_at is the newest occurrence"
    assert "MIN(occurred_at)" in sql, "first_seen_at is the oldest occurrence"
