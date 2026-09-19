"""Writing whose date is unknown, carried the whole way through.

Forty-three voice transcripts — the largest single body of the owner's
thinking in the archive — carry no date and never will unless the original
export turns up. Until now they could not be committed at all: reflection_date
and occurred_at were both NOT NULL, so "the day is unknown" had nowhere to be
recorded and the import refused the batch rather than guess.

ADR-0013 says a date is read or it is absent, never invented. These tests pin
the second half, which was previously unreachable, and they mostly pin what
undated writing must *not* be able to do: reach a window engine, acquire a
date from the clock, or be quietly counted inside a span it was never shown to
fall within.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from agent.database import db, themes
from agent.importing import store
from agent.importing.service import ImportError_, ImportService
from agent.lifelong import LifelongEngine
from agent.narrative import NarrativeFormatter
from agent.trackers.reflections import ReflectionService

RECORDING = "Talked myself out of the gambit and then took it anyway, twice the effort."
LATER = "Same thing again with the second opening, certain and overcommitted."


def _theme(user_id: int, summary: str = "certainty and size") -> int:
    return db.create_theme(user_id, [0.1] * 1536, summary,
                           datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())


def _occur(theme_id: int, n: int, *, dated: bool, start_days_ago: int = 800,
           every: int = 60, offset: int = 0) -> None:
    """n occurrences on one theme, spread across roughly two years, or none."""
    for i in range(n):
        when = None
        if dated:
            when = (datetime.now(UTC)
                    - timedelta(days=start_days_ago - i * every)).isoformat()
        db.add_theme_occurrence(theme_id, "reflection", offset + i,
                                f"a sentence {offset + i}", 0.8, when)
    db.update_theme_stats(theme_id)


# --- an absence is storable, and only on purpose -------------------------------

def test_an_entry_can_record_that_its_day_is_unknown(test_user):
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content=RECORDING, undated=True)

    assert service.get_reflection(reflection_id)["reflection_date"] is None


def test_omitting_a_date_still_means_today(test_user):
    """The app's own path is unchanged: no date supplied means "written now".

    This is the guard that makes the absence deliberate. If a missing argument
    could reach NULL, every entry typed without a date would silently become
    undated and drop out of every window.
    """
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content=RECORDING)

    assert service.get_reflection(reflection_id)["reflection_date"] == date.today()


def test_the_same_undated_words_are_not_imported_twice(test_user):
    """De-duplication keys on (user, day, text). Two NULLs are never equal in a
    unique index, so without a sentinel the guard would silently switch off for
    exactly the entries that have no date."""
    service = ReflectionService(test_user["id"])
    service.create_reflection(content=RECORDING, undated=True,
                              content_hash="a" * 64)

    import psycopg2
    with pytest.raises(psycopg2.errors.UniqueViolation):
        service.create_reflection(content=RECORDING, undated=True,
                                  content_hash="a" * 64)


# --- an undated occurrence is counted, and reaches no window --------------------

def test_a_window_engine_never_sees_an_undated_occurrence(test_user):
    """The safety property the whole design rests on.

    Six engines measure rates, gaps and co-occurrence in days. Rather than add
    a null check to each — where one omission is a wrong number nobody can see
    — the default read excludes undated rows, so an engine has to ask.
    """
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 3, dated=True)
    _occur(theme_id, 5, dated=False, offset=100)

    assert len(themes.get_occurrences(theme_id)) == 3
    assert len(themes.get_occurrences(theme_id, include_undated=True)) == 8


def test_the_two_counts_are_kept_apart(test_user):
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 3, dated=True)
    _occur(theme_id, 5, dated=False, offset=100)

    theme = db.get_theme_by_id(theme_id)
    assert theme["occurrence_count"] == 3, "what the engines gate on stays dated"
    assert theme["undated_occurrence_count"] == 5


def test_a_theme_with_no_dated_evidence_claims_no_span(test_user):
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=False)

    assert db.get_theme_by_id(theme_id)["span_is_undated"] is True


# --- lifelong, the one reader that counts them ---------------------------------

def test_undated_occurrences_are_counted_without_a_span(test_user):
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=False)

    found = LifelongEngine(test_user["id"]).analyze_theme(db.get_theme_by_id(theme_id))

    assert found["occurrence_count"] == 6
    assert found["undated_occurrences"] == 6
    assert found["lifelong_label"] == "undated"


def test_a_count_only_finding_carries_no_dates_at_all(test_user):
    """Not "None where a date would go" — absent. A downstream reader that
    falls back when a key is missing must not find a key to read."""
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=False)

    found = LifelongEngine(test_user["id"]).analyze_theme(db.get_theme_by_id(theme_id))

    for key in ("first_seen_at", "last_seen_at", "span_days", "days_since_last",
                "densest_year", "active_months"):
        assert key not in found, f"{key} does not exist for undated writing"


def test_an_undated_finding_is_not_described_as_recent(test_user):
    """The live hazard. The formatter fills a missing first_seen_at with "the
    recent period", so the default phrasing would have dated, in a sentence,
    the writing whose distinguishing property is that its date is unknown."""
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=False)

    found = LifelongEngine(test_user["id"]).analyze_theme(db.get_theme_by_id(theme_id))
    rendered = NarrativeFormatter.format_insight({**found, "engine_name": "lifelong"})

    assert "recent" not in rendered.lower()
    assert "no date" in rendered


def test_a_partly_dated_theme_is_not_described_as_wholly_undated(test_user):
    """The live error this caught. Theme 39 had ten undated occurrences and two
    dated ones — too few to carry a span, so it took the undated phrasing, which
    then reported all twelve as coming from writing that carries no date. Two of
    them did not. A count and a claim about where it came from are two
    measurements, and this is what merging them looks like (ADR-0009).
    """
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 2, dated=True, start_days_ago=400, every=2)
    _occur(theme_id, 10, dated=False, offset=100)

    found = LifelongEngine(test_user["id"]).analyze_theme(db.get_theme_by_id(theme_id))
    rendered = NarrativeFormatter.format_insight({**found, "engine_name": "lifelong"})

    assert found["occurrence_count"] == 12
    assert found["undated_occurrences"] == 10
    assert found["dated_occurrences"] == 2
    assert "12 times, 10 of them" in rendered, rendered


def test_undated_occurrences_are_not_added_to_a_dated_count(test_user):
    """A span covers the dated occurrences only. Quoting a larger number beside
    it would claim the rest fell inside it (ADR-0009)."""
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 4, dated=True)
    _occur(theme_id, 5, dated=False, offset=100)

    found = LifelongEngine(test_user["id"]).analyze_theme(db.get_theme_by_id(theme_id))

    assert found["occurrence_count"] == 4, "the headline is what the span covers"
    assert found["undated_occurrences"] == 5
    assert found["lifelong_label"] != "undated", "there is a real span here"


def test_a_short_dated_burst_is_still_skipped(test_user):
    """The count-only path is for undated evidence, not a second chance for a
    theme whose occurrences are simply too close together."""
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 4, dated=True, start_days_ago=400, every=2)

    assert LifelongEngine(test_user["id"]).analyze_theme(
        db.get_theme_by_id(theme_id)) is None


# --- discovery must not date what it clusters -----------------------------------

def test_clustering_undated_entries_does_not_date_them(test_user, process_queue):
    """The leak this test exists for reached live data.

    Discovery built its entry list with `item.get("occurred_at") or
    item["created_at"]` — invisible while every entry had a date, and the moment
    undated ones existed it dated four of them to the second they were embedded.
    Two themes then recorded a span beginning today for writing that has no date
    at all, which on any screen reads as "you wrote this this morning".

    The same `or` had already been removed from one query; it was still in the
    other. So this asserts the property rather than the line: nothing undated
    comes out of clustering with a date.
    """
    service = ReflectionService(test_user["id"])
    for i in range(6):
        service.create_reflection(
            content=f"{RECORDING} Certain about the gambit again, recording {i}.",
            undated=True)
    process_queue()

    from agent.persistence import PersistenceEngine
    PersistenceEngine(test_user["id"]).discover_themes()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT COUNT(*) FROM theme_occurrences o
                         JOIN reflections r ON r.id = o.source_id
                        WHERE o.source_type = 'reflection' AND r.user_id = %s
                          AND r.reflection_date IS NULL
                          AND o.occurred_at IS NOT NULL;""", (test_user["id"],))
        assert cur.fetchone()[0] == 0, "an undated entry acquired a date"


def test_a_theme_built_only_from_undated_writing_claims_no_span(test_user, process_queue):
    service = ReflectionService(test_user["id"])
    for i in range(6):
        service.create_reflection(
            content=f"{RECORDING} Certain about the gambit again, recording {i}.",
            undated=True)
    process_queue()

    from agent.persistence import PersistenceEngine
    PersistenceEngine(test_user["id"]).discover_themes()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT COUNT(*) FROM themes
                        WHERE user_id = %s AND occurrence_count > 0;""",
                    (test_user["id"],))
        dated_themes = cur.fetchone()[0]
    assert dated_themes == 0, "no theme may report dated occurrences here"


# --- both surfaces show what the undated writing added ---------------------------

def _lifelong_cards(user_id: int) -> list[dict]:
    from agent.insights_service import InsightsService
    return [r for r in InsightsService(user_id)._normalize() if r["engine"] == "lifelong"]


def test_the_insights_page_shows_a_finding_with_no_span(test_user):
    """The regression this caught on live data. The card read span_days and
    densest_year with hard subscripts; a count-only finding has neither, so the
    first one raised KeyError inside the loop and the page silently dropped it —
    and every finding after it, had one sorted earlier. Chat rendered both new
    findings throughout; the Insights page showed neither."""
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=False)

    cards = _lifelong_cards(test_user["id"])

    assert [c["theme_id"] for c in cards] == [theme_id]
    assert cards[0]["label"] == "undated"
    assert "without a date" in cards[0]["headline_metric"]


def test_one_undated_finding_does_not_take_the_others_with_it(test_user):
    dated = _theme(test_user["id"], "a long-running one")
    _occur(dated, 4, dated=True)
    undated = _theme(test_user["id"], "an undated one")
    _occur(undated, 6, dated=False, offset=100)

    assert {c["theme_id"] for c in _lifelong_cards(test_user["id"])} == {dated, undated}


def test_a_dated_card_shows_its_undated_occurrences_separately(test_user):
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 4, dated=True)
    _occur(theme_id, 5, dated=False, offset=100)

    card = _lifelong_cards(test_user["id"])[0]
    rows = {m["label"]: m["value"] for m in card["measures"]}

    assert rows["Occurrences"] == 4, "the span's number stays the dated count"
    assert rows["Without a date"] == 5
    assert "5 more undated" in card["headline_metric"]


def test_the_sentence_says_what_the_undated_writing_added(test_user):
    """Computed and never shown is the same as not counted, to the owner."""
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 4, dated=True)
    _occur(theme_id, 5, dated=False, offset=100)

    found = LifelongEngine(test_user["id"]).analyze_theme(db.get_theme_by_id(theme_id))
    rendered = NarrativeFormatter.format_insight({**found, "engine_name": "lifelong"})

    assert "appeared 4 times since" in rendered
    assert "5 more times in writing that carries no date" in rendered
    # Concentration is measured by year; an occurrence with no year is neither
    # concentrated nor spread, so the label must attach to the dated ones.
    assert "those occurrences were" in rendered


def test_without_undated_evidence_the_sentence_is_unchanged(test_user):
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 4, dated=True)

    found = LifelongEngine(test_user["id"]).analyze_theme(db.get_theme_by_id(theme_id))
    rendered = NarrativeFormatter.format_insight({**found, "engine_name": "lifelong"})

    assert "no date" not in rendered
    assert "; its occurrences were" in rendered


# --- nothing present-tense may be said about undated-only evidence --------------

def test_undated_only_evidence_is_not_reported_as_persisting(test_user):
    """Two live themes reached this. With no dated occurrence the resolution
    engine compared two empty windows and called the result `persisting`, 0 and
    0 — a pattern that is "still going" on no evidence at all."""
    from agent.resolution import ResolutionEngine
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=False)

    result = ResolutionEngine(test_user["id"]).analyze_theme(theme_id, force_recompute=True)

    assert result["resolution_label"] == "unsupported"
    assert result["current_state_supported"] is False


def test_neither_surface_shows_it_even_at_the_lowest_floor(test_user, journalled_recently):
    """The label was only hidden by accident: low confidence under a `medium`
    floor, and no recent writing for the coverage gate. Remove both and it
    reached the screen."""
    from agent.insights_service import InsightsService
    from agent.preferences import UserPreferencesService
    journalled_recently()  # enough recent writing that the coverage gate opens
    UserPreferencesService(test_user["id"]).update_pref("min_confidence", "low")
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=False)

    svc = InsightsService(test_user["id"])
    shown = svc._apply_policy(svc._normalize())

    assert not [i for i in shown if i["engine"] == "resolution"]


def test_a_span_is_described_in_the_past_tense(test_user):
    """"Is spread" read a two-year count as though it were how things are this
    morning — for the one engine that passes the coverage gate on the promise
    that it claims nothing about now."""
    from agent.insights_service import InsightsService
    theme_id = _theme(test_user["id"])
    _occur(theme_id, 6, dated=True)  # medium confidence clears the default floor

    svc = InsightsService(test_user["id"])
    summary = svc.list_summaries()[0]
    card = _lifelong_cards(test_user["id"])[0]

    assert summary["headline"]["line2"].startswith("recurred")
    assert "I keep noticing" not in svc._iris_read(card)
    assert "claim about how things are now" in svc._methodology("lifelong")


def test_rewriting_snippets_reaches_undated_occurrences(test_user):
    """The maintenance rewrite read occurrences through the dated-only default,
    so it silently skipped exactly the rows it existed to repair."""
    from agent.persistence import PersistenceEngine
    reflection_id = ReflectionService(test_user["id"]).create_reflection(
        content=RECORDING, undated=True)
    theme_id = _theme(test_user["id"])
    db.add_theme_occurrence(theme_id, "reflection", reflection_id,
                            "Anchor: Self-Reflection | Source: Reflection | Content: x",
                            0.9, None)

    PersistenceEngine(test_user["id"]).refresh_snippets()

    occurrence = themes.get_occurrences(theme_id, include_undated=True)[0]
    assert occurrence["snippet"] == RECORDING


# --- resolving the absence later -----------------------------------------------

def test_dating_an_entry_dates_the_occurrences_it_already_has(test_user):
    """The reason storing an absence is acceptable at all. If supplying the day
    did not reach the occurrences, the owner would answer the question and see
    nothing change."""
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content=RECORDING, undated=True)
    theme_id = _theme(test_user["id"])
    db.add_theme_occurrence(theme_id, "reflection", reflection_id, RECORDING, 0.9, None)
    db.update_theme_stats(theme_id)

    when = date.today() - timedelta(days=400)
    assert db.set_reflection_date(reflection_id, test_user["id"], when) == 1

    theme = db.get_theme_by_id(theme_id)
    assert theme["occurrence_count"] == 1
    assert theme["undated_occurrence_count"] == 0
    assert theme["span_is_undated"] is False
    assert len(themes.get_occurrences(theme_id)) == 1


def test_a_date_already_read_from_the_writing_is_never_overwritten(test_user):
    """Filling a blank is not the same act as correcting a date the export
    stated. Only the first is what this path is for."""
    service = ReflectionService(test_user["id"])
    known = date.today() - timedelta(days=30)
    reflection_id = service.create_reflection(content=RECORDING, reflection_date=known)

    assert db.set_reflection_date(reflection_id, test_user["id"],
                                  date.today() - timedelta(days=400)) == 0
    assert service.get_reflection(reflection_id)["reflection_date"] == known


# --- importing -------------------------------------------------------------------

@pytest.fixture
def staged(test_user):
    """Three undated recordings, numbered by their source as the real ones are."""
    batch_id = store.create_batch(test_user["id"], "text", "transcripts.md", None)
    store.replace_items(batch_id, test_user["id"], [
        {"source_name": f"Telegram Voice Transcripts.md#{i:03d}",
         "content": f"{RECORDING} Recording number {i}.",
         "content_hash": f"{i:064d}", "entry_date": None}
        for i in (3, 1, 2)
    ])
    return batch_id


def test_an_unresolved_date_still_blocks_a_commit(test_user, staged):
    """Where every batch starts. "The parser found nothing" is not an answer,
    and the refusal that has always caught it is unchanged."""
    with pytest.raises(ImportError_, match="no date"):
        ImportService(test_user["id"]).commit(staged)


def test_accepting_that_the_day_is_unknown_lets_the_batch_commit(test_user, staged):
    service = ImportService(test_user["id"])
    ids = [i["id"] for i in store.list_items(staged, test_user["id"])]
    service.bulk(ids, "accept_unknown_date")

    result = service.commit(staged)

    assert result["committed"] == 3
    assert all(r["reflection_date"] is None
               for r in ReflectionService(test_user["id"]).get_reflections(limit=10))


def test_accepting_is_reversible(test_user, staged):
    service = ImportService(test_user["id"])
    ids = [i["id"] for i in store.list_items(staged, test_user["id"])]
    service.bulk(ids, "accept_unknown_date")
    service.bulk(ids, "require_date")

    with pytest.raises(ImportError_, match="no date"):
        service.commit(staged)


def test_the_order_the_export_recorded_survives_the_commit(test_user, staged):
    """Dates are unknown; the sequence is not. A transcript file numbers its
    recordings, so the order is read from the source exactly as a date would
    be — and it is staged out of order here to prove the numbering is what is
    being read, not the insertion order."""
    service = ImportService(test_user["id"])
    ids = [i["id"] for i in store.list_items(staged, test_user["id"])]
    service.bulk(ids, "accept_unknown_date")
    service.commit(staged)

    page = db.get_journal_page(test_user["id"], limit=10)
    by_sequence = sorted(page, key=lambda r: r["entry_sequence"])

    assert [r["entry_sequence"] for r in by_sequence] == [1, 2, 3]
    assert [r["content"][-2] for r in by_sequence] == ["1", "2", "3"]


def test_a_committed_undated_entry_is_not_stamped_with_today(test_user, staged):
    """The failure this whole path exists to prevent, at the one place it could
    still happen: create_reflection fills a missing date with today's."""
    service = ImportService(test_user["id"])
    ids = [i["id"] for i in store.list_items(staged, test_user["id"])]
    service.bulk(ids, "accept_unknown_date")
    service.commit(staged)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM reflections WHERE user_id = %s "
                    "AND reflection_date IS NOT NULL;", (test_user["id"],))
        assert cur.fetchone()[0] == 0


# --- paging ----------------------------------------------------------------------

def test_paging_reaches_the_end_of_the_undated_entries(test_user):
    """A NULL date makes the keyset comparison evaluate to NULL, so undated rows
    dropped out of every page after the first — and a page ending inside them
    handed back a NULL cursor, which the query read as "no cursor" and answered
    with page one. Forever.
    """
    service = ReflectionService(test_user["id"])
    service.create_reflection(content="a dated one",
                              reflection_date=date.today() - timedelta(days=5))
    for i in range(5):
        service.create_reflection(content=f"undated {i}", undated=True,
                                  entry_sequence=i)

    seen, cursor = [], None
    for _ in range(10):  # generous; 6 entries at 2 a page is 3 rounds
        page = db.get_journal_page(test_user["id"], limit=2, before=cursor)
        if not page:
            break
        seen.extend(r["id"] for r in page)
        cursor = (page[-1]["reflection_date"], page[-1]["id"])

    assert len(seen) == 6, "every entry appears"
    assert len(set(seen)) == 6, "and none of them twice"


def test_the_dated_entries_come_first(test_user):
    service = ReflectionService(test_user["id"])
    service.create_reflection(content="a dated one",
                              reflection_date=date.today() - timedelta(days=5))
    service.create_reflection(content="undated", undated=True)

    page = db.get_journal_page(test_user["id"], limit=10)

    assert page[0]["reflection_date"] is not None
    assert page[-1]["reflection_date"] is None
