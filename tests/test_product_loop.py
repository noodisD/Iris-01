"""
The product loop: raw entries in, themes and insights out.

These tests exist because the loop was broken end to end and nothing noticed.
`discover_themes()` — the only way a theme is ever *born* — was reachable only
from the CLI, so a user of the web app accumulated embeddings forever and never
formed a single theme. Every downstream engine therefore had nothing to analyse.

They also pin the boundary of what counts as evidence: deliberate logging
(journal entries, reflections, completed habits) does; conversation with Iris
and skipped habits do not.
"""

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.journal_entry import JournalEntry
from agent.persistence import PersistenceEngine
from agent.pipeline import run_processing_pipeline
from agent.trackers.habits import HabitTracker
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _themes_for(user_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, summary FROM themes WHERE user_id = %s;", (user_id,))
        return cur.fetchall()


def _occurrences_for(user_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT o.source_type, o.source_id FROM theme_occurrences o
            JOIN themes t ON t.id = o.theme_id WHERE t.user_id = %s;
            """,
            (user_id,),
        )
        return cur.fetchall()


def test_journal_entries_through_the_api_produce_a_theme(client, test_user, mock_pipeline_logic):
    """THE product-loop test: write through the HTTP API, get a theme out.

    Before discovery was wired into the pipeline this failed at zero themes no
    matter how much the user wrote.
    """
    user_id = test_user["id"]
    assert _themes_for(user_id) == [], "user should start with no themes"

    # PERSISTENCE_MIN_CLUSTER_SIZE is 5, so five related entries is the floor
    # at which a proto-theme may form.
    for i in range(5):
        r = client.post("/api/journal", json={"lines": [f"Work Stress keeps building, day {i}"], "energy": 4})
        assert r.status_code == 200, r.text

    themes = _themes_for(user_id)
    assert themes, "five related journal entries must produce at least one theme"

    # And the theme is made of those entries, not of nothing.
    occs = _occurrences_for(user_id)
    assert len(occs) >= 5
    assert {t for t, _ in occs} == {"reflection"}

    # The insights endpoint is reachable and shaped correctly off the back of it.
    r = client.get("/api/insights")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_chat_messages_are_never_theme_material(test_user, mock_pipeline_logic):
    """Talking to Iris must not manufacture evidence about the user.

    Messages are still embedded for semantic retrieval; they are simply not
    clustered into themes and not matched against them.
    """
    user_id = test_user["id"]
    for i in range(6):
        mid = db.create_conversation_message(user_id, "s1", "user", f"Work Stress again, {i}")
        run_processing_pipeline("message", mid)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM embeddings WHERE source_type='message';")
        assert cur.fetchone()[0] >= 6, "messages should still be embedded for retrieval"

    assert PersistenceEngine(user_id).discover_themes() == []
    assert _themes_for(user_id) == [], "conversation must not create themes"


def test_pipeline_embeds_the_row_it_was_asked_for(test_user, monkeypatch):
    """Two rows in 'processing' must not be able to swap identities.

    The pipeline used to mark one row 'processing' and then read back *any* row
    in that status, so one entry's text could be embedded under another's id —
    taking the other row's user_id with it.
    """
    user_id = test_user["id"]
    first = db.create_journal_entry(user_id, "ALPHA one distinctive entry", {})
    second = db.create_journal_entry(user_id, "BETA a quite different entry", {})

    # Leave `first` stuck mid-flight, exactly as a crashed run would.
    db.update_processing_status("journal_entry", first, "processing")

    seen = []
    monkeypatch.setattr(
        "agent.pipeline.generate_embedding",
        lambda text, model=None: seen.append(text) or [0.42] * 1536,
    )
    monkeypatch.setattr(
        "agent.persistence.PersistenceEngine._generate_theme_summary", lambda s, e: "T"
    )

    run_processing_pipeline("journal_entry", second)

    assert seen, "the pipeline should have embedded something"
    assert "BETA" in seen[0], f"embedded the wrong row's text: {seen[0]!r}"
    assert "ALPHA" not in seen[0]


def test_skipping_a_habit_is_not_evidence_for_it(test_user, mock_pipeline_logic):
    """A skip means the pattern did not happen; it must not reinforce the theme."""
    user_id = test_user["id"]
    tracker = HabitTracker(user_id)
    habit_id = tracker.create_habit(name="Yoga", description="unwind", category="health")

    tracker.log_skip(habit_id, reason="too tired")

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM embeddings e
            JOIN habit_completions hc ON hc.id = e.source_id
            WHERE e.source_type = 'habit_completion' AND hc.is_skipped IS TRUE;
            """
        )
        assert cur.fetchone()[0] == 0, "a skip must not be embedded as evidence"


def test_journal_entry_service_creates_an_entry(test_user):
    """Regression: `journals` was used but never imported, so this raised
    NameError and the broad except reported a friendly failure to the user."""
    out = JournalEntry(test_user["id"]).create_entry(
        wellbeing={"mood": 7}, ideas=["- an idea"], goals=[], execution=[]
    )
    assert "Journal Entry Created" in out, out

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM journal_entries WHERE user_id = %s;", (test_user["id"],))
        assert cur.fetchone()[0] == 1


def test_date_ranged_reflections_are_filtered_in_the_database(test_user, mock_pipeline_logic):
    """A date range used to be applied in Python *after* fetching only the most
    recent rows, so any window outside them came back silently empty — which is
    why the weekly review compared a week against nothing once the user had
    written more than the fetch limit."""
    from datetime import date, timedelta

    from agent.trackers.reflections import ReflectionService

    svc = ReflectionService(test_user["id"])
    for i in range(35):
        svc.create_reflection(content=f"this week {i}", energy_level=8)
    svc.create_reflection(
        content="last week", energy_level=3, reflection_date=date.today() - timedelta(days=9)
    )

    prior = svc.get_reflections(
        start_date=date.today() - timedelta(days=12), end_date=date.today() - timedelta(days=7)
    )
    assert [r["content"] for r in prior] == ["last week"]


def test_cross_theme_engines_run_on_the_ingest_path(test_user, mock_pipeline_logic, monkeypatch):
    """Leverage and decision impact are pairwise and do not cache on read, so
    the chat path reads their cache tables directly. Nothing on the HTTP path
    used to fill those tables — only the Insights screen and the CLI ran the
    engines — so two of the six engines were silent in the chat context unless
    the user happened to open Insights first.

    They must now run when an occurrence changes the theme graph.
    """
    from agent.decision_impact import DecisionImpactEngine
    from agent.leverage import LeverageEngine
    from agent.trackers.reflections import ReflectionService

    calls = {"leverage": 0, "impact": 0}
    real_leverage = LeverageEngine.analyze_all_leverage
    real_impact = DecisionImpactEngine.analyze_all_anchors

    def spy_leverage(self, *a, **k):
        calls["leverage"] += 1
        return real_leverage(self, *a, **k)

    def spy_impact(self, *a, **k):
        calls["impact"] += 1
        return real_impact(self, *a, **k)

    monkeypatch.setattr(LeverageEngine, "analyze_all_leverage", spy_leverage)
    monkeypatch.setattr(DecisionImpactEngine, "analyze_all_anchors", spy_impact)

    svc = ReflectionService(test_user["id"])
    for i in range(6):
        svc.create_reflection(content=f"Work Stress is building again {i}", energy_level=3)

    assert _themes_for(test_user["id"]), "precondition: the entries formed a theme"
    assert calls["leverage"] > 0, "leverage never ran on the ingest path"
    assert calls["impact"] > 0, "decision impact never ran on the ingest path"


def test_cross_theme_refresh_never_breaks_ingestion(test_user, mock_pipeline_logic, monkeypatch):
    """The refresh is an optimisation of the chat context, not part of storing
    the entry. If it raises, the entry must still be saved and embedded."""
    from agent.leverage import LeverageEngine
    from agent.trackers.reflections import ReflectionService

    monkeypatch.setattr(
        LeverageEngine, "analyze_all_leverage",
        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("engine exploded")),
    )

    svc = ReflectionService(test_user["id"])
    reflection_id = svc.create_reflection(content="Work Stress once more", energy_level=3)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT processing_status FROM reflections WHERE id = %s;", (reflection_id,))
        assert cur.fetchone()[0] == "complete", "ingestion must survive a failing refresh"
