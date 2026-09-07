"""
How IRIS behaves when things go wrong.

Each of these pins a failure mode that used to be silent: a health check that
reported ok while the database was unreachable, an LLM outage that was written
into the conversation as Iris's own words, and a deleted entry that left its
evidence behind.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import iris_api
from agent.core import PersonalAICompanion
from agent.database import db
from agent.trackers.habits import HabitTracker
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_is_ok_when_the_database_answers(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"


def test_health_reports_503_when_the_database_is_unreachable(client, monkeypatch):
    """It used to return {"status": "ok"} unconditionally, so every data route
    could 500 while monitoring saw a green service."""
    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(iris_api.db, "ping", boom)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["checks"]["database"] == "down"


def test_an_llm_outage_is_not_persisted_as_iris_speaking(test_user, monkeypatch):
    """A provider failure must not become conversation history.

    The first version of this test mocked Intelligence.chat to raise, so it
    asserted the behaviour of its own mock and passed while the real path was
    still broken: _chat_openai() caught the exception and returned
    "OpenAI API error: ..." as an ordinary string, which core.chat() then stored
    as the assistant's reply and re-fed as context on later turns. It now fails
    at the SDK boundary, which is where a real outage occurs.
    """
    monkeypatch.setattr(
        "agent.persistence.PersistenceEngine._generate_theme_summary", lambda s, e: "T"
    )

    companion = PersonalAICompanion(user_id=test_user["id"])
    companion.intelligence.openai_client = MagicMock()
    companion.intelligence.openai_client.chat.completions.create.side_effect = TimeoutError(
        "synthetic provider timeout"
    )

    with pytest.raises(Exception) as caught:
        companion.chat("are you there?")
    assert "synthetic provider timeout" in str(caught.value)

    history = db.get_chat_history(test_user["id"], limit=50)
    assert [m["content"] for m in history] == ["are you there?"], (
        "the user's message is kept, but no assistant turn should be invented"
    )
    assert not any("API error" in m["content"] for m in history), (
        "an error string must never be persisted as Iris speaking"
    )


def test_provider_errors_are_raised_not_returned(monkeypatch):
    """The narrow version of the above, at the seam itself — no database needed."""
    from agent.intelligence import Intelligence

    intelligence = Intelligence.__new__(Intelligence)
    intelligence.model = "gpt-4.1-mini"
    intelligence.openai_client = MagicMock()
    intelligence.openai_client.chat.completions.create.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        intelligence.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s")


def test_deleting_a_reflection_removes_its_evidence(test_user, mock_pipeline_logic):
    """embeddings and theme_occurrences reference sources by (type, id) rather
    than by foreign key, so a deleted entry used to leave an embedding that
    still matched searches and an occurrence that still counted as evidence."""
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content="Work Stress today", energy_level=4)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM embeddings WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        assert cur.fetchone()[0] == 1, "precondition: the entry was embedded"

    service.delete_reflection(reflection_id)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM embeddings WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        assert cur.fetchone()[0] == 0, "the embedding must go with the entry"
        cur.execute(
            "SELECT count(*) FROM theme_occurrences WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        assert cur.fetchone()[0] == 0, "the occurrence must go with the entry"


# --- caches must not outlive the question they answer -----------------------

def test_a_stale_resolution_verdict_is_recomputed(test_user, mock_pipeline_logic):
    """Resolution compares a rolling recent window against a rolling baseline,
    so the same data yields a different answer as weeks pass. A cached verdict
    used to count as fresh forever if its timestamp was non-null, so a verdict
    computed years ago could still be served today."""
    from datetime import timedelta

    from agent.database import themes
    from agent.resolution import ResolutionEngine
    from agent.timeutils import utc_now

    now = utc_now()
    theme_id = themes.create_theme(
        user_id=test_user["id"], centroid_embedding=[0.2] * 1536, summary="TTL Theme",
        first_seen_at=(now - timedelta(days=80)).isoformat(), last_seen_at=now.isoformat(),
        occurrence_count=0,
    )
    for i in range(6):
        themes.add_occurrence(
            theme_id=theme_id, source_type="reflection", source_id=950000 + i,
            snippet=f"x{i}", similarity_score=0.9,
            occurred_at=(now - timedelta(days=40 + i)).isoformat(),
        )

    engine = ResolutionEngine(test_user["id"])
    fresh = engine.analyze_theme(theme_id, force_recompute=True)

    # Backdate the cache far past its TTL and corrupt the label, so serving it
    # would be unmistakable.
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE pattern_resolutions SET resolution_label = 'STALE-VERDICT',
               last_computed_at = now() - interval '400 days'
               WHERE pattern_type = 'theme' AND pattern_id = %s;""",
            (theme_id,),
        )
        conn.commit()

    assert engine.analyze_theme(theme_id)["resolution_label"] == fresh["resolution_label"], (
        "a cache older than its TTL must be recomputed, not served"
    )


def test_a_recent_resolution_verdict_is_still_served(test_user, mock_pipeline_logic):
    """The TTL must not turn the cache off altogether."""
    from datetime import timedelta

    from agent.database import themes
    from agent.resolution import ResolutionEngine
    from agent.timeutils import utc_now

    now = utc_now()
    theme_id = themes.create_theme(
        user_id=test_user["id"], centroid_embedding=[0.3] * 1536, summary="Warm Theme",
        first_seen_at=(now - timedelta(days=80)).isoformat(), last_seen_at=now.isoformat(),
        occurrence_count=0,
    )
    for i in range(6):
        themes.add_occurrence(
            theme_id=theme_id, source_type="reflection", source_id=960000 + i,
            snippet=f"y{i}", similarity_score=0.9,
            occurred_at=(now - timedelta(days=40 + i)).isoformat(),
        )

    engine = ResolutionEngine(test_user["id"])
    engine.analyze_theme(theme_id, force_recompute=True)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE pattern_resolutions SET resolution_label = 'CACHED-VALUE'
               WHERE pattern_type = 'theme' AND pattern_id = %s;""",
            (theme_id,),
        )
        conn.commit()

    assert engine.analyze_theme(theme_id)["resolution_label"] == "CACHED-VALUE"


# --- corrections must propagate to everything derived from the entry ---------

def _embedding_count(source_type, source_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM embeddings WHERE source_type = %s AND source_id = %s;",
            (source_type, source_id),
        )
        return cur.fetchone()[0]


def _occurrence_count(source_type, source_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM theme_occurrences WHERE source_type = %s AND source_id = %s;",
            (source_type, source_id),
        )
        return cur.fetchone()[0]


def test_editing_an_entry_refreshes_what_was_derived_from_it(test_user, mock_pipeline_logic):
    """An edit used to change only the row. The embedding still described the
    original text and the theme occurrence still quoted it, so a sentence the
    user had removed remained searchable and quotable."""
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content="Work Stress about the merger", energy_level=4)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT vector FROM embeddings WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        before = cur.fetchone()[0]

    service.update_reflection(reflection_id, content="Poor Sleep, nothing about work")

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT vector FROM embeddings WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        row = cur.fetchone()
    assert row is not None, "the edited entry must still be searchable"
    assert list(row[0]) != list(before), (
        "the embedding must describe the corrected text, not the original"
    )


def test_undoing_a_habit_tick_removes_its_evidence(test_user, mock_pipeline_logic):
    """Un-ticking deleted the completion row but left its embedding and theme
    occurrence, so a day the user took back still counted towards the pattern."""
    tracker = HabitTracker(test_user["id"])
    habit_id = tracker.create_habit(name="Yoga", description="unwind", category="health")
    completion_id = tracker.log_completion(habit_id)

    assert _embedding_count("habit_completion", completion_id) == 1

    db.uncomplete_habit(habit_id)

    assert _embedding_count("habit_completion", completion_id) == 0, (
        "an undone completion must not leave an embedding behind"
    )
    assert _occurrence_count("habit_completion", completion_id) == 0, (
        "an undone completion must not keep counting as evidence"
    )
