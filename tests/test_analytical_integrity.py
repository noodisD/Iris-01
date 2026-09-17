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
        emb.get_evidence_style.return_value = (0, None)  # below the minimum: raw space
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
    assert "distance_threshold=1.0 - cluster_threshold" in src
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
        emb.get_evidence_style.return_value = (0, None)  # below the minimum: raw space
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


# --- support must not count the same observation twice ----------------------

def _leverage_pair(source_times, target_times):
    """Run the real analyze_pair with only the occurrence store mocked."""
    from agent.leverage import LeverageEngine

    engine = LeverageEngine(user_id=1)
    captured = {}
    with patch.object(engine, "_get_occurrences",
                      side_effect=lambda t, i, since: (
                          source_times if i == 1 else target_times)), \
         patch.object(engine, "ev_engine"), \
         patch("agent.leverage.leverage_repo") as repo:
        repo.create_or_update_pair.side_effect = (
            lambda **kw: captured.update(kw)
        )
        result = engine.analyze_pair("theme", 1, "theme", 2)
    return result, captured


def test_a_same_day_pair_is_not_counted_as_both_forward_and_simultaneous():
    """Five isolated pairs an hour apart produced five forward plus five
    simultaneous counts — support of ten from five events — and a maximum
    directional lift drawn from pairs _is_simultaneous calls neutral."""
    # 30 days apart, so no target is followed by the *next* source within the
    # 7-day lag: the fixture isolates the same-day pair itself.
    base = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    sources = [base + timedelta(days=30 * i) for i in range(5)]
    targets = [t + timedelta(hours=1) for t in sources]

    result, stored = _leverage_pair(sources, targets)

    assert result is not None
    assert stored["cooccurrence_count"] == 5, (
        f"five events must be five units of support, got {stored['cooccurrence_count']}"
    )
    assert result["directional_lift"] == 0.0, (
        "same-day evidence is neutral, so it cannot produce directional lift"
    )


def test_a_next_day_follower_is_still_directional_evidence():
    """The negative control must not have been bought by ignoring the lag."""
    base = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    sources = [base + timedelta(days=30 * i) for i in range(5)]
    targets = [t + timedelta(days=2) for t in sources]

    result, stored = _leverage_pair(sources, targets)

    assert result is not None
    assert stored["cooccurrence_count"] == 5
    assert result["directional_lift"] == 1.0, (
        "every source followed by a target two days later is maximal forward evidence"
    )


def test_tension_divides_shared_days_by_active_days():
    """The numerator counts days the themes shared; the denominator counted raw
    events, so a second entry on an already-active day changed the rate without
    changing the coexistence it reports."""
    from agent.tension import TensionEngine

    engine = TensionEngine(user_id=1)
    base = datetime(2026, 6, 1, tzinfo=UTC)

    def occ(day, n=1):
        return [{"occurred_at": base + timedelta(days=day, hours=h),
                 "source_type": "journal_entry", "source_id": day * 10 + h}
                for h in range(n)]

    sparse = occ(0) + occ(1) + occ(2)
    # The very same three days, but each theme logged three times a day.
    dense = occ(0, 3) + occ(1, 3) + occ(2, 3)

    with patch("agent.tension.themes") as th:
        th.get_occurrences.side_effect = lambda tid: sparse
        sparse_metrics = engine._calculate_cooccurrence_metrics(1, 2)

        th.get_occurrences.side_effect = lambda tid: dense
        dense_metrics = engine._calculate_cooccurrence_metrics(1, 2)

    assert sparse_metrics["cooccurrence_count"] == 3
    assert dense_metrics["cooccurrence_count"] == 3, (
        "a busy day is still one shared day"
    )
    assert sparse_metrics["cooccurrence_rate"] == dense_metrics["cooccurrence_rate"], (
        f"the same three shared days must give the same rate: "
        f"{sparse_metrics['cooccurrence_rate']} vs {dense_metrics['cooccurrence_rate']}"
    )
    assert dense_metrics["cooccurrence_rate"] == 1.0, (
        "three shared days out of three active days is total coexistence"
    )


# --- silence is measured between events, not to a window edge ---------------

def _resolution_label(ages_in_days):
    """Classify a theme whose occurrences are these many days old."""
    from agent.resolution import ResolutionEngine

    engine = ResolutionEngine(user_id=1)
    now = datetime.now(UTC)
    timestamps = sorted(now - timedelta(days=d) for d in ages_in_days)
    recent_start, baseline_end, baseline_start = engine._get_time_windows()

    recent = sum(1 for t in timestamps if t >= recent_start)
    past = sum(1 for t in timestamps if baseline_start <= t < baseline_end)
    rate_recent = recent / 21
    rate_past = past / 90
    attenuation = engine._calculate_attenuation_score(rate_recent, rate_past)
    gap = engine._get_gap_detected(list(timestamps), recent_start)
    return engine._classify_resolution(past, recent, attenuation, gap)


def test_a_real_gap_between_events_is_a_reappearance():
    """Occurrences 32, 31, 30 and 1 days old contain a 29-day silence. The gap
    was measured to the window boundary instead, so this read as persisting."""
    assert _resolution_label([32, 31, 30, 1]) == "reappearing"


def test_a_short_gap_is_not_a_reappearance():
    """The 29-day fixture must not have been bought by always saying yes."""
    assert _resolution_label([30, 29, 28, 16]) != "reappearing"


def test_old_only_history_is_not_reported_as_stabilized():
    """With both windows empty the attenuation score is zero, which used to mean
    'little change in rate' — a steady ongoing rate claimed for a theme with no
    evidence in 111 days."""
    assert _resolution_label([150, 140, 135, 130]) != "stabilized"


def test_a_genuinely_steady_theme_is_still_stabilized():
    """The control: evidence on both sides of the comparison, at the same rate
    and with no silence long enough to count as a gap."""
    ages = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95, 105]
    assert _resolution_label(ages) == "stabilized"


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


# --- impact needs an observed baseline and independent episodes -------------

def _impact(anchor_ages, target_ages, observation_age):
    """Run the real _calculate_impact against occurrences of these ages."""
    from agent.decision_impact import DecisionImpactEngine

    engine = DecisionImpactEngine(user_id=1)
    now = datetime.now(UTC)
    anchors = sorted(now - timedelta(days=d) for d in anchor_ages)
    targets = sorted(now - timedelta(days=d) for d in target_ages)

    with patch.object(engine, "_get_all_occurrences", return_value=targets), \
         patch.object(engine, "_observation_start",
                      return_value=now - timedelta(days=observation_age)), \
         patch.object(engine, "ev_engine"), \
         patch("agent.decision_impact.decision_impacts"):
        return engine._calculate_impact(1, anchors, "theme", 2)


def test_a_steady_cadence_on_a_short_history_is_not_an_increase():
    """40 days of perfectly constant activity, anchors 15-17 days ago: the
    baseline divided by a full 60 days regardless of the record only going back
    40, so the same steady cadence scored as a 179% increase at medium
    confidence. A new user's first weeks are not evidence of change."""
    result = _impact(
        anchor_ages=[17, 16, 15],
        target_ages=list(range(1, 41)),   # one a day for 40 days
        observation_age=40,
    )
    assert result is None or result["effect_direction"] == "none", result


def test_a_real_emergence_after_an_observed_baseline_is_still_found():
    """The control: an observed, genuinely empty baseline followed by activity."""
    result = _impact(
        anchor_ages=[60, 45, 30],
        target_ages=list(range(16, 30)),  # only after the last anchor
        observation_age=200,
    )
    assert result is not None
    assert result["effect_direction"] in ("emergence", "increase"), result


def test_one_episode_written_up_ten_times_is_not_ten_confirmations():
    """Ten anchor entries at one moment produced `emergence` at high confidence
    with consistency 1.0 from five target events. They are ten entries about one
    episode, and their follow-up windows score the same events ten times."""
    now_ages = [40] * 10
    result = _impact(
        anchor_ages=now_ages,
        target_ages=[35, 34, 33, 32, 31],
        observation_age=300,
    )
    assert result is None, (
        f"one episode cannot supply the minimum number of anchors, got {result}"
    )


def test_separate_episodes_still_count_separately():
    """The control: the same number of anchors, genuinely spread apart."""
    result = _impact(
        anchor_ages=[120, 90, 60],
        target_ages=[115, 114, 85, 84, 55, 54, 53],
        observation_age=300,
    )
    assert result is not None, "well-separated anchors are independent episodes"


def test_the_persisted_anchor_count_is_the_cohort_actually_evaluated():
    """anchor_count stored every anchor on record while the calculation judged
    only those with elapsed follow-up and an observed baseline."""
    result = _impact(
        anchor_ages=[120, 90, 60, 1],     # the last one has no elapsed follow-up
        target_ages=[115, 114, 85, 84, 55, 54, 53],
        observation_age=300,
    )
    assert result is not None
    assert result["anchor_count"] == 3, (
        f"four anchors on record, three judged, got {result['anchor_count']}"
    )


# --- confidence must use the time coverage it measures ----------------------

def test_instantaneous_evidence_cannot_be_high_confidence():
    """coverage_days was computed and then ignored, so ten reflections saved in
    the same second scored 1.0 and 'high' across zero days of coverage."""
    from agent.confidence import ConfidenceEngine

    now = datetime.now(UTC)
    burst = [now] * 10

    result = ConfidenceEngine().compute_confidence("theme", 1, burst)

    assert result["time_coverage_days"] == 0
    assert result["confidence_level"] != "high", (
        f"ten entries in one moment is one observation, got {result}"
    )


def test_the_same_evidence_spread_over_time_is_high_confidence():
    """The control: the count is identical, only the span differs."""
    from agent.confidence import ConfidenceEngine

    now = datetime.now(UTC)
    spread = [now - timedelta(days=d) for d in range(10)]

    result = ConfidenceEngine().compute_confidence("theme", 1, spread)

    assert result["time_coverage_days"] >= 7
    assert result["confidence_level"] == "high", result


def test_the_evaluated_cohort_is_the_episodes_that_had_a_baseline():
    """Censoring removes the *earliest* episodes — the ones closest to the start
    of the record — so the evaluated cohort is the tail, not the head."""
    from agent.decision_impact import DecisionImpactEngine

    engine = DecisionImpactEngine(user_id=1)
    now = datetime.now(UTC)
    # The 95-day-old anchor sits only 5 days after observation began, so it has
    # no baseline; the other two do.
    anchors = sorted(now - timedelta(days=d) for d in (95, 60, 30))
    # Dense before the last episode, silent after it, so there is a real effect
    # to report and the calculation reaches the confidence step.
    targets = sorted(now - timedelta(days=d) for d in range(31, 100))

    captured = {}
    with patch.object(engine, "_get_all_occurrences", return_value=targets), \
         patch.object(engine, "_observation_start", return_value=now - timedelta(days=100)), \
         patch.object(engine, "ev_engine"), \
         patch("agent.decision_impact.decision_impacts"), \
         patch.object(engine.conf_engine, "compute_confidence",
                      side_effect=lambda pt, pid, ts, d=None, sources=None: captured.update(
                          {"timestamps": list(ts)}) or {
                          "confidence_level": "medium", "confidence_score": 0.5,
                          "data_points_count": len(ts), "time_coverage_days": 30,
                          "consistency_score": 1.0, "recency_score": 0.5}):
        engine._calculate_impact(1, anchors, "theme", 2)

    assert captured["timestamps"], "some episodes must survive censoring"
    oldest_evaluated = min(captured["timestamps"])
    assert (now - oldest_evaluated).days < 95, (
        "the episode without an observed baseline must not be in the cohort"
    )


# --- confidence in an absence is not confidence in a recent event -----------

def _absence(baseline_count, days_silent, during, before, span=45.0):
    from agent.confidence import ConfidenceEngine

    return ConfidenceEngine().compute_absence_confidence(
        baseline_count=baseline_count,
        days_silent=days_silent,
        silence_threshold_days=21,
        observed_days_during=during,
        observed_days_before=before,
        # These fixtures describe patterns that ran for weeks before stopping.
        # The span was implicit when it did not exist as an input; a burst
        # confined to one day is now a separate case, tested in test_coverage.
        baseline_span_days=span,
    )


def test_a_well_observed_dissipation_can_be_high_confidence():
    """A dissipation needs 21 days of silence, at which point the ordinary
    recency term is exp(-21/30) = 0.4966 — permanently below the 0.5 the 'high'
    branch demands. The strongest possible dissipation could never be trusted."""
    result = _absence(baseline_count=12, days_silent=60, during=40, before=45)
    assert result["confidence_level"] == "high", result


def test_a_longer_silence_is_more_convincing_not_less():
    """The ordinary model has the sign backwards here: ninety days of silence
    after twenty occurrences scored 'low' because the newest evidence was old."""
    short = _absence(baseline_count=12, days_silent=22, during=15, before=16)
    long = _absence(baseline_count=12, days_silent=90, during=60, before=62)
    assert long["confidence_score"] > short["confidence_score"], (short, long)


def test_a_silence_nobody_observed_proves_nothing():
    """The guard that keeps this honest: a fortnight's holiday is not a resolved
    pattern. Inverting the sign without this would be worse than the bug.

    One logged day against forty-five now fails two gates — the continuity ratio
    and the minimum number of observed days — and both say the same thing."""
    result = _absence(baseline_count=20, days_silent=60, during=1, before=45)
    assert result["confidence_level"] == "low", result


def test_continuity_is_measured_against_the_user_s_own_rate():
    """Someone who journals weekly must not read as absent six days in seven."""
    weekly = _absence(baseline_count=12, days_silent=60, during=8, before=8)
    assert weekly["confidence_level"] == "high", weekly


def test_a_thin_pattern_that_stops_is_not_high_confidence():
    """Support still matters: two occurrences stopping is not a resolution."""
    result = _absence(baseline_count=2, days_silent=60, during=40, before=45)
    assert result["confidence_level"] == "low", result


def test_resolution_uses_the_absence_model_only_for_dissipation():
    """Every other label is a claim about what is happening now and keeps the
    ordinary recency-decayed score."""
    import inspect

    from agent.resolution import ResolutionEngine

    src = inspect.getsource(ResolutionEngine.analyze_theme)
    assert "if label == 'dissipated':" in src
    assert "_absence_confidence" in src


def test_the_dissipated_anchor_filter_is_reachable():
    """decision_impact required 'dissipated' AND 'high', which the arithmetic
    above made impossible, so dead patterns went on being anchors."""
    import inspect

    from agent.decision_impact import DecisionImpactEngine

    src = inspect.getsource(DecisionImpactEngine._get_candidate_anchors)
    assert "('medium', 'high')" in src, (
        "the filter must accept a confidence level a dissipation can actually reach"
    )
