"""Archive-wide currentness, source invalidation, and exact saved opinions."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from agent import discovery, discovery_worker
from agent.database import db
from agent.episodes import Episode, SYSTEM_PROMPT as EXTRACTION_PROMPT
from agent.connections import FIELD_PROMPT
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint
from agent.intelligence import Intelligence as ProviderIntelligence
from tests.test_personal_patterns import NarrativeDecisions


def _state(user_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT source_generation, review_generation, stage
                         FROM discovery_state WHERE user_id = %s""", (user_id,))
        return cur.fetchone()


def _episode(reflection_id, n: int, day: date | None = None) -> Episode:
    day = day or datetime.now().astimezone().date() - timedelta(days=n)
    response = "I agreed before checking my capacity"
    text = (f"At the distinct meeting #{n}, someone was waiting for my answer. "
            f"{response}. I recorded the event separately.")
    return Episode(actor="self", record_kind="event", situation="someone was waiting for my answer",
                   response=response, demand=None, information=None, feeling=None, concern=None,
                   immediate_outcome=None, later_outcome=None, explanation=None,
                   self_report=None, domain=None, recorded_on=day,
                   citations=(Citation(entry_id=reflection_id, entry_date=day, text=text),))


def test_empty_completed_read_is_ready_without_synthesis_provider(test_user):
    owner = test_user["id"]
    source = db.create_reflection(owner, "I wrote a journal entry about a recipe I have not tried.")
    discovery_worker.process_reflection(source)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT source_revision, extraction_version, reader_version,
                              omitted_accounts, omitted_fields FROM discovery_reads
                       WHERE reflection_id = %s""", (source,))
        assert cur.fetchone() == (1, 4, discovery.READER_VERSION, 0, 0)
    discovery.process_user(owner)
    rows, coverage = discovery.patterns(owner)
    assert rows == []
    assert coverage["entryCount"] == 0
    assert discovery.insights(owner)[0] == []
    assert _state(owner)[2] == "ready"
    before = _state(owner)[0]
    db.update_reflection(source, content="Changed journal text about a recipe.")
    assert _state(owner)[0] == before + 1
    assert discovery.patterns(owner) == ([], None)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM discovery_views WHERE user_id = %s", (owner,))
        assert cur.fetchone()[0] == 0
    discovery_worker.process_reflection(source)
    discovery.process_user(owner)
    assert discovery.patterns(owner)[0] == []


def test_current_dynamic_snapshot_note_and_membership_correction(test_user, monkeypatch):
    owner = test_user["id"]
    episodes = []
    for n in (1, 2, 3):
        day = datetime.now().astimezone().date() - timedelta(days=n)
        text = (f"At the distinct meeting #{n}, someone was waiting for my answer. "
                "I agreed before checking my capacity. I recorded the event separately.")
        source = db.create_reflection(owner, text, reflection_date=day)
        episode = _episode(source, n, day)
        episodes.append(episode)
        with db.connection() as conn, conn.cursor() as cur:
            sources = discovery._source_rows(cur, owner, {source: 1})
            discovery._store_reading(cur, owner, [episode.as_dict()], source_revisions={source: 1},
                                     locked_sources=sources)
            conn.commit()
    model = NarrativeDecisions(episodes)
    class ScriptedModel:
        estimate = staticmethod(ProviderIntelligence.estimate)

        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            return model.chat(**kwargs)

    monkeypatch.setattr(discovery, "Intelligence", ScriptedModel)
    monkeypatch.setattr(discovery, "load", list)  # Unmapped personal dynamics remain visible.
    discovery.process_user(owner)
    cards, coverage = discovery.patterns(owner)
    assert len(cards) == 1
    assert coverage["entryCount"] == 3
    card = cards[0]
    assert card.evidence_state == "recurring"
    assert card.lens_matches == []
    detail = discovery.pattern(owner, card.id)
    assert len(detail["accounts"]) == len(detail["groups"][card.id]) == 3
    aid = account_fingerprint(episodes[0].as_dict())
    approved = discovery.set_feedback(owner, "dynamic", card.id, "all", card.snapshot,
                                      "rings_true", "This part fits")
    assert approved["feedback"]["verdict"] == "rings_true"
    assert discovery.patterns(owner)[0][0].feedback.note == "This part fits"
    with pytest.raises(discovery.EvidenceChanged):
        discovery.set_feedback(owner, "dynamic", card.id, "all", card.snapshot,
                               "does_not", "Stale reply")
    current = discovery.patterns(owner)[0][0]
    discovery.set_membership_feedback(owner, card.id, aid, "all", current.snapshot,
                                      "no", "This occasion differs")
    assert discovery.patterns(owner) == ([], None)
    assert _state(owner)[1] == 1
    discovery.process_user(owner)  # Cached draft; only the dated interpretations change.
    revised = discovery.patterns(owner)[0][0]
    assert revised.independent_group_count == 2
    assert revised.feedback.needs_review
    corrected = discovery.pattern(owner, card.id)
    rows = corrected["memberships"][card.id]
    assert next(row for row in rows if row["accountId"] == aid)["excluded"] is True
    assert next(row for row in rows if row["accountId"] == aid)["verdictNote"] == "This occasion differs"
    assert revised.claim_hash != card.claim_hash
    with pytest.raises(discovery.EvidenceChanged):
        discovery.set_membership_feedback(owner, card.id, aid, "all", current.snapshot,
                                          None, None)
    source_id = episodes[0].citations[0].entry_id
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO discovery_legacy_feedback
                       (user_id, kind, legacy_key, source_ids, payload)
                       VALUES (%s, 'occasion', 'old-label', %s, '{}'::jsonb)""",
                    (owner, [source_id]))
        conn.commit()
    db.update_reflection(source_id, content="A revised source with no request.")
    assert discovery.patterns(owner) == ([], None)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT data, is_current FROM discovery_accounts
                       WHERE user_id = %s AND id = %s""", (owner, aid))
        assert cur.fetchone() == (None, False)
        cur.execute("""SELECT verdict, note FROM discovery_membership_feedback
                       WHERE user_id = %s AND account_id = %s""", (owner, aid))
        assert cur.fetchone() == ("no", "This occasion differs")
    db.delete_reflection(source_id)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM discovery_accounts
                       WHERE user_id = %s AND id = %s""", (owner, aid))
        assert cur.fetchone()[0] == 0
        cur.execute("""SELECT count(*) FROM discovery_membership_feedback
                       WHERE user_id = %s AND account_id = %s""", (owner, aid))
        assert cur.fetchone()[0] == 0
        cur.execute("""SELECT count(*) FROM discovery_legacy_feedback
                       WHERE user_id = %s AND kind = 'occasion' AND legacy_key = 'old-label'""",
                    (owner,))
        assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("rejected_field", ["response", "immediate_outcome"])
def test_reader_requires_contextual_support_for_each_source_field(
        test_user, monkeypatch, rejected_field):
    owner = test_user["id"]
    text = ("When we discussed the landlord, I walked to the door. "
            "My brother said he felt relieved; I did not feel relieved.")
    source = db.create_reflection(owner, text)

    class CheckedReading:
        def chat(self, *, messages, system_prompt, **kwargs):
            if system_prompt == EXTRACTION_PROMPT:
                return json.dumps({"episodes": [{
                    "actor": "self", "recordKind": "event",
                    "situation": "When we discussed the landlord",
                    "response": "I walked to the door",
                    "immediateOutcome": "felt relieved",
                    "quotes": [{"entryId": source, "sourceType": "reflection", "text": text}]}]})
            if system_prompt == FIELD_PROMPT:
                aid = "account"
                return json.dumps({"fields": [
                    {"field": field,
                     "verdict": "not_stated" if field == rejected_field else "supported",
                     "refs": [] if field == rejected_field else [
                         {"accountId": aid, "field": field, "citationIndex": 0}]}
                    for field in ("situation", "response", "immediate_outcome")]})
            raise AssertionError("unexpected provider stage")

    monkeypatch.setattr(discovery_worker, "Intelligence", lambda **kwargs: CheckedReading())
    discovery_worker.process_reflection(source)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT omitted_accounts, omitted_fields
                       FROM discovery_reads WHERE reflection_id = %s""", (source,))
        omitted_accounts, omitted_fields = cur.fetchone()
        cur.execute("""SELECT data FROM discovery_accounts
                       WHERE user_id = %s AND reflection_id = %s AND is_current""",
                    (owner, source))
        rows = cur.fetchall()
    if rejected_field == "response":
        assert (omitted_accounts, omitted_fields) == (1, 0)
        assert rows == []
    else:
        assert (omitted_accounts, omitted_fields) == (0, 1)
        assert len(rows) == 1
        assert rows[0][0]["immediateOutcome"] is None
