"""Themes are found in what differs between entries, not in the voice they share.

On the owner's first real import one theme took 121 of the 132 entries that
grouped at all. Nothing was wrong with any single threshold: one person's
writing shares a voice so strong that every raw similarity cleared the bar, and
a centroid averaged from a few entries looked like all of them. These tests
build that shape from synthetic vectors — a shared voice plus a topic plus a
little noise, with cross-topic similarity above every raw threshold — so the
failure and the fix can both be seen without real data (ADR-0014).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import numpy as np

from agent.constants import PERSISTENCE_MATCH_THRESHOLD, PERSISTENCE_STYLE_MIN_ENTRIES
from agent.persistence import PersistenceEngine
from agent.prompt_labels import PROMPT_LABELS, strip_prompt_labels

DIM = 1536


def _journal(topics: int = 3, per_topic: int = 8, seed: int = 5):
    """cos(same topic) ≈ 0.95 and cos(different topics) ≈ 0.80: both above
    every raw threshold, as in the real journal."""
    rng = np.random.default_rng(seed)
    basis = np.linalg.qr(rng.normal(size=(DIM, 1 + topics + topics * per_topic)))[0].T
    voice, topic_dirs, noise = basis[0], basis[1:1 + topics], basis[1 + topics:]
    vectors, labels = [], []
    for t in range(topics):
        for k in range(per_topic):
            v = np.sqrt(0.80) * voice + np.sqrt(0.15) * topic_dirs[t] + np.sqrt(0.05) * noise[t * per_topic + k]
            vectors.append(v / np.linalg.norm(v))
            labels.append(t)
    return np.array(vectors), labels


def _rows(vectors):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [{"vector": v.tolist(), "source_type": "reflection", "source_id": 100 + i,
             "created_at": base + timedelta(days=i), "occurred_at": base + timedelta(days=i)}
            for i, v in enumerate(vectors)]


def _discover(vectors, style):
    """The real discover_themes, with only the database boundary replaced."""
    engine = PersistenceEngine(user_id=1)
    created = []
    with patch("agent.persistence.db") as emb:
        emb.get_unassigned_embeddings.return_value = _rows(vectors)
        emb.get_evidence_style.return_value = style
        with patch.object(engine, "_create_theme_from_cluster",
                          side_effect=lambda vecs, entries: created.append(
                              [e["source_id"] - 100 for e in entries]) or {"id": len(created)}):
            engine.discover_themes()
    return created


def test_raw_comparison_merges_distinct_topics_into_one_theme():
    """The failure, reproduced. Kept so the reason for ADR-0014 stays checkable."""
    vectors, _ = _journal()
    pairwise = vectors @ vectors.T
    assert pairwise[~np.eye(len(vectors), dtype=bool)].min() > PERSISTENCE_MATCH_THRESHOLD

    created = _discover(vectors, style=(0, None))  # too little evidence: raw space
    assert len(created) == 1 and len(created[0]) == len(vectors)


def test_removing_the_shared_voice_separates_the_topics():
    vectors, labels = _journal()
    created = _discover(vectors, style=(PERSISTENCE_STYLE_MIN_ENTRIES, vectors.mean(axis=0)))

    assert len(created) == 3, f"expected one theme per topic, got sizes {[len(c) for c in created]}"
    for members in created:
        assert len({labels[i] for i in members}) == 1, "a theme mixed topics"
        assert len(members) == 8


def test_an_entry_joins_the_closest_theme_not_the_first():
    """Themes come back largest first; first-past-the-bar gave every borderline
    entry to the biggest theme."""
    rng = np.random.default_rng(1)
    entry = rng.normal(size=DIM); entry /= np.linalg.norm(entry)
    p, q = rng.normal(size=DIM), rng.normal(size=DIM)
    for v in (p, q):
        v -= entry * float(v @ entry); v /= np.linalg.norm(v)
    far = entry + 0.9 * p     # cos ≈ 0.74, above the raw bar
    near = entry + 0.3 * q    # cos ≈ 0.96

    engine = PersistenceEngine(user_id=1)
    with patch("agent.persistence.db") as emb:
        th = emb
        emb.get_evidence_style.return_value = (0, None)
        th.get_themes_by_origin.return_value = [
            {"id": 1, "centroid_embedding": far.tolist(), "occurrence_count": 50},
            {"id": 2, "centroid_embedding": near.tolist(), "occurrence_count": 3},
        ]
        matched = engine.check_persistence(entry.tolist(), "reflection", 7, "text",
                                           datetime(2026, 1, 1, tzinfo=UTC))
    assert matched == 2
    assert th.add_theme_occurrence.call_args.kwargs["theme_id"] == 2


def test_prompt_labels_are_stripped_and_the_writing_is_kept():
    text = ("What went well: finished the deck\n\nKey insight: small steps work\n\n"
            "Ideas:\n- try pomodoro\n\nNotes: slept badly")
    out = strip_prompt_labels(text)
    for label in ("What went well", "Key insight", "Ideas", "Notes"):
        assert label not in out
    for words in ("finished the deck", "small steps work", "try pomodoro", "slept badly"):
        assert words in out


def test_ordinary_colons_in_writing_survive():
    text = "Today: rough. Done with it: finally."
    assert strip_prompt_labels(text) == text


def test_every_label_the_importer_writes_is_stripped():
    from agent.importing.adapters import _IRIS_OG_SECTIONS

    written = {label for _, label in _IRIS_OG_SECTIONS} | {"Notes", "Ideas", "Goals", "Done"}
    assert written <= set(PROMPT_LABELS)


def test_the_embedding_is_made_from_the_writing_alone(test_user, monkeypatch):
    from agent import pipeline
    from agent.database import db
    from agent.trackers.reflections import ReflectionService

    seen = []
    real = pipeline.generate_embedding
    monkeypatch.setattr(pipeline, "generate_embedding",
                        lambda text, model=None: seen.append(text) or real(text, model=model))
    content = "What went well: shipped the importer\n\nKey insight: review before commit"
    rid = ReflectionService(test_user["id"]).create_reflection(content=content)
    pipeline.run_processing_pipeline("reflection", rid)

    assert seen and "What went well" not in seen[-1] and "shipped the importer" in seen[-1]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT content FROM reflections WHERE id = %s;", (rid,))
        assert cur.fetchone()[0] == content, "the stored entry keeps its labels"


def test_a_rebuild_replaces_themes_and_the_analyses_cached_against_them(test_user):
    from agent.database import db
    from agent.pipeline import rebuild_themes, run_processing_pipeline
    from agent.trackers.reflections import ReflectionService

    uid = test_user["id"]
    service = ReflectionService(uid)
    ids = [service.create_reflection(content=f"Poor Sleep again {i}") for i in range(6)]
    for rid in ids:
        run_processing_pipeline("reflection", rid)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM themes WHERE user_id = %s;", (uid,))
        before = [r[0] for r in cur.fetchall()]
        assert before, "the fixture should form a theme"
        cur.execute("""INSERT INTO pattern_confidence (pattern_type, pattern_id, confidence_level, confidence_score, last_computed_at)
                       VALUES ('theme', %s, 'high', 0.9, now());""", (before[0],))
        conn.commit()

    result = rebuild_themes(uid)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM themes WHERE user_id = %s;", (uid,))
        after = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM pattern_confidence WHERE pattern_type = 'theme' AND pattern_id = ANY(%s);", (before,))
        stale = cur.fetchone()[0]
        cur.execute("""SELECT count(DISTINCT o.source_id) FROM theme_occurrences o
                       JOIN themes t ON t.id = o.theme_id WHERE t.user_id = %s;""", (uid,))
        grouped = cur.fetchone()[0]

    assert result["removed"] == len(before)
    assert after and not set(after) & set(before), "themes are found again under new ids"
    assert stale == 0, "an analysis of a theme that no longer exists must not survive"
    assert grouped == len(ids)


def test_a_bridge_between_two_themes_does_not_destroy_both():
    """DBSCAN linked two tight groups through one entry resembling both, and the
    cohesion check then rejected the whole chain: neither theme formed. This is
    what happened on the owner's journal after three entries were re-embedded."""
    rng = np.random.default_rng(9)
    a = rng.normal(size=DIM); a /= np.linalg.norm(a)
    b = rng.normal(size=DIM); b -= a * float(b @ a); b /= np.linalg.norm(b)
    b = 0.3 * a + np.sqrt(1 - 0.09) * b                 # cos(a, b) = 0.3

    def near(anchor):
        p = rng.normal(size=DIM); p -= anchor * float(p @ anchor); p /= np.linalg.norm(p)
        v = 0.99 * anchor + np.sqrt(1 - 0.99 ** 2) * p
        return v / np.linalg.norm(v)

    group_a = [near(a) for _ in range(6)]
    group_b = [near(b) for _ in range(6)]
    bridge = (a + b) / np.linalg.norm(a + b)            # ≈ 0.80 to both groups
    vectors = np.array(group_a + group_b + [bridge])

    created = _discover(vectors, style=(0, None))       # raw space, creation bar 0.78
    themes = [set(m) for m in created if len(m) >= 5]
    assert len(themes) == 2, f"both groups must survive, got sizes {[len(m) for m in created]}"
    first, second = set(range(6)), set(range(6, 12))
    for t in themes:
        assert not (t & first and t & second), "a theme mixed the two groups"
