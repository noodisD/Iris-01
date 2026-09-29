"""Only complete, current, source-backed discovery work may become visible."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from agent import discovery, discovery_worker, work_queue
from agent.database import db
from agent.episodes import EXTRACTION_VERSION, ReadUnavailable
from agent.library import library_hash, load


PASSAGE = "I noticed the room was loud; I waited quietly and felt calm afterwards."
OTHER = "I noticed the room was loud; I spoke up and felt disappointed afterwards."


def _entry(user_id, content=PASSAGE, **kwargs):
    return db.create_reflection(user_id, content, **kwargs)


def _account(reflection_id, date, content=PASSAGE, *, response=None):
    response = response or ("I waited quietly" if content == PASSAGE else "I spoke up")
    outcome = "felt calm afterwards" if content == PASSAGE else "felt disappointed afterwards"
    return {"actor": "self", "modality": "happened", "domain": "daily life",
            "situation": "the room was loud", "response": response, "outcome": outcome,
            "quotes": [{"entryId": reflection_id, "text": content, "sourceType": "reflection"}]}


def _stored_account(reflection_id, date, content=PASSAGE):
    from agent.episodes import verified_episodes
    source = {"id": reflection_id, "date": date, "content": content,
              "source_type": "reflection"}
    return verified_episodes([_account(reflection_id, date, content)], [source])[0].as_dict()


def _revision(reflection_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT discovery_revision, reflection_date FROM reflections WHERE id = %s", (reflection_id,))
        return cur.fetchone()


def _reading(user_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT o.id, o.response, o.citations, o.is_current, l.pattern_id,
                              l.is_current, l.owner_verdict, l.verdict_note, l.owner_tone
                         FROM occasions o LEFT JOIN pattern_labels l ON l.occasion_id = o.id
                        WHERE o.user_id = %s ORDER BY o.id, l.pattern_id""", (user_id,))
        return cur.fetchall()


def _completed(reflection_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT source_revision, extraction_version, library_hash, omitted_accounts
                         FROM discovery_reads WHERE reflection_id = %s""", (reflection_id,))
        return cur.fetchone()


def _script(monkeypatch, raw, *, chosen=None, on_read=None):
    """Model only at the actual provider seam; real reader validates spans."""
    import json

    called = []
    pattern_id = chosen or load()[0].id

    class Model:
        def __init__(self, *, model):
            self.model = model

        def chat(self, **kwargs):
            called.append("read")
            if on_read:
                on_read()
            return json.dumps({"episodes": raw})

    def labels(subjects, episodes, intelligence):
        called.append("label")
        return {sid: ({0: {"tone": "better", "size": "moderate"}}
                      if sid == pattern_id and episodes else {})
                for sid, _, _ in subjects}, {}

    monkeypatch.setattr(discovery_worker, "Intelligence", Model)
    monkeypatch.setattr(discovery_worker, "label_many", labels)
    return called, pattern_id


def _import(user_id, reflection_id, episodes, labels):
    revision, _ = _revision(reflection_id)
    return discovery.load_reading(user_id, episodes, labels,
                                  source_revisions={reflection_id: revision},
                                  extraction_version=EXTRACTION_VERSION,
                                  library_hash=library_hash(load()))


def _labels_for(episodes, pattern_id, *, tone="better"):
    patterns = load()
    digest = library_hash(patterns)
    from agent.discovery import comparable_positions
    positions = comparable_positions(episodes)
    return {"accounts": len(positions), "extractionVersion": EXTRACTION_VERSION,
            "libraryHash": digest,
            "labels": {p.id: ({"0": {"tone": tone, "size": "moderate"}}
                              if positions and p.id == pattern_id else {})
                       for p in patterns} if positions else {},
            "by": {p.id: "scripted" for p in patterns}}


def test_successful_empty_read_retires_previous_evidence_and_is_not_retried(test_user, monkeypatch):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)
    revision, date = _revision(reflection_id)
    pattern_id = load()[0].id
    episode = _stored_account(reflection_id, date)
    _import(user_id, reflection_id, [episode], _labels_for([episode], pattern_id))
    calls, _ = _script(monkeypatch, [])
    discovery_worker.process_reflection(reflection_id)  # matching completion: no model call
    assert calls == []
    db.update_reflection(reflection_id, content=PASSAGE + " Another detail.")
    discovery_worker.process_reflection(reflection_id)
    assert calls == ["read"]
    assert not discovery._labels(user_id)
    assert _reading(user_id)[0][3] is False
    assert _completed(reflection_id) == (_revision(reflection_id)[0], EXTRACTION_VERSION,
                                         library_hash(load()), 0)
    discovery_worker.process_reflection(reflection_id)
    assert calls == ["read"]


def test_failed_or_incomplete_model_pass_does_not_publish_partial_read(test_user, monkeypatch):
    reflection_id = _entry(test_user["id"])
    calls, pattern_id = _script(monkeypatch, [_account(reflection_id, _revision(reflection_id)[1])])
    def fail_second(subjects, episodes, model):
        calls.append("label")
        if calls.count("label") == 2:
            raise ReadUnavailable("Labelling provider failure")
        return {sid: ({0: {"tone": "better", "size": "moderate"}} if sid == pattern_id else {})
                for sid, _, _ in subjects}, {}
    monkeypatch.setattr(discovery_worker, "label_many", fail_second)
    with pytest.raises(ReadUnavailable):
        discovery_worker.process_reflection(reflection_id)
    assert _completed(reflection_id) is None
    assert _reading(test_user["id"]) == []
    monkeypatch.setattr(discovery_worker, "label_many", lambda s, e, m: (
        {sid: {} for sid, _, _ in s[:-1]}, {}))
    with pytest.raises(ReadUnavailable, match="incomplete"):
        discovery_worker.process_reflection(reflection_id)
    assert _completed(reflection_id) is None


def test_unavailable_read_retries_without_replacing_completion_or_logging_prose(test_user, monkeypatch):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)
    date = _revision(reflection_id)[1]
    account = _stored_account(reflection_id, date)
    _import(user_id, reflection_id, [account], _labels_for([account], load()[0].id))
    previous = _completed(reflection_id)
    db.update_reflection(reflection_id, content=OTHER)

    class Unavailable:
        def __init__(self, *, model):
            pass

        def chat(self, **kwargs):
            raise RuntimeError(PASSAGE)

    monkeypatch.setattr(discovery_worker, "Intelligence", Unavailable)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE processing_queue SET next_attempt_at = NOW() + interval '1 day'
                        WHERE source_type = 'reflection' AND source_id = %s""", (reflection_id,))
        conn.commit()
    assert work_queue.process_due() == (0, 1)
    assert _completed(reflection_id) == previous
    assert discovery._labels(user_id) == []
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT attempts, last_error FROM processing_queue
                        WHERE source_type = 'discovery' AND source_id = %s""", (reflection_id,))
        attempts, error = cur.fetchone()
    assert attempts == 1 and "provider failure" in error
    assert PASSAGE not in error


def test_new_generation_survives_old_generation_failure(test_user, monkeypatch):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)

    class EditingOutage:
        def __init__(self, *, model):
            pass

        def chat(self, **kwargs):
            db.update_reflection(reflection_id, content=OTHER)
            raise RuntimeError(PASSAGE)

    monkeypatch.setattr(discovery_worker, "Intelligence", EditingOutage)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE processing_queue SET next_attempt_at = NOW() + interval '1 day'
                        WHERE source_type = 'reflection' AND source_id = %s""", (reflection_id,))
        conn.commit()
    assert work_queue.process_due() == (0, 1)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT attempts, last_error FROM processing_queue
                        WHERE source_type = 'discovery' AND source_id = %s""", (reflection_id,))
        row = cur.fetchone()
    assert row == (0, None)


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_source_change_during_read_discards_old_pass(test_user, monkeypatch, action):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)
    was = _revision(reflection_id)[0]
    def change():
        if action == "edit":
            db.update_reflection(reflection_id, content=OTHER)
        else:
            db.delete_reflection(reflection_id)
    _script(monkeypatch, [_account(reflection_id, _revision(reflection_id)[1])], on_read=change)
    discovery_worker.process_reflection(reflection_id)
    assert not _reading(user_id)
    assert _completed(reflection_id) is None
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT generation FROM processing_queue WHERE source_type='discovery' AND source_id=%s",
                    (reflection_id,))
        job = cur.fetchone()
    if action == "edit":
        assert _revision(reflection_id)[0] > was and job is not None
    else:
        assert job is None


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_published_citations_are_retired_on_source_change(test_user, action):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)
    account = _stored_account(reflection_id, _revision(reflection_id)[1])
    _import(user_id, reflection_id, [account], _labels_for([account], load()[0].id))
    assert len(discovery._labels(user_id)) == 1
    if action == "edit":
        db.update_reflection(reflection_id, content=OTHER)
        assert discovery._labels(user_id) == []
        assert _reading(user_id)[0][3] is False
    else:
        db.delete_reflection(reflection_id)
        assert _reading(user_id) == []
        assert _completed(reflection_id) is None


def test_simultaneous_claims_cannot_overwrite_completed_read(test_user, monkeypatch):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)
    both_read = Barrier(2)
    raw = [_account(reflection_id, _revision(reflection_id)[1])]
    _script(monkeypatch, raw, on_read=lambda: both_read.wait(timeout=10))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(discovery_worker.process_reflection, reflection_id) for _ in range(2)]
        for result in futures:
            result.result(timeout=20)
    assert len(_reading(user_id)) == 1
    assert len(discovery._labels(user_id)) == 1
    assert _completed(reflection_id) is not None


def test_replay_and_disappearing_label_keep_only_identical_account_judgment(test_user, monkeypatch):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)
    _, date = _revision(reflection_id)
    pattern_id = load()[0].id
    account = _stored_account(reflection_id, date)
    first = _labels_for([account], pattern_id)
    assert _import(user_id, reflection_id, [account], first)["occasions_added"] == 1
    occasion_id = _reading(user_id)[0][0]
    discovery.set_occasion_verdict(user_id, pattern_id, occasion_id, "no", "Not how I see it")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE pattern_labels SET owner_tone = 'worse' WHERE occasion_id = %s", (occasion_id,))
        conn.commit()
    assert _import(user_id, reflection_id, [account], first)["occasions_already_there"] == 1
    assert discovery._labels(user_id)[0]["tone"] == "worse"
    no_labels = _labels_for([account], pattern_id)
    no_labels["labels"][pattern_id] = {}
    _import(user_id, reflection_id, [account], no_labels)
    assert discovery._labels(user_id) == []
    _import(user_id, reflection_id, [account], first)
    saved = discovery._labels(user_id)[0]
    assert saved["owner_verdict"] == "no" and saved["verdict_note"] == "Not how I see it"
    assert saved["tone"] == "worse"
    new_account = _stored_account(reflection_id, date, PASSAGE)
    new_account["response"] = "I waited quietly and felt calm afterwards"
    _import(user_id, reflection_id, [new_account], _labels_for([new_account], pattern_id))
    current = discovery._labels(user_id)
    assert len(current) == 1 and current[0]["owner_verdict"] is None
    assert current[0]["tone"] == "better"


def test_current_labels_require_matching_completed_read_and_all_sources(test_user):
    user_id = test_user["id"]
    reflection_id = _entry(user_id)
    account = _stored_account(reflection_id, _revision(reflection_id)[1])
    _import(user_id, reflection_id, [account], _labels_for([account], load()[0].id))
    assert len(discovery._labels(user_id)) == 1
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE discovery_reads SET library_hash = %s WHERE reflection_id = %s",
                    ("0" * 64, reflection_id))
        conn.commit()
    assert discovery._labels(user_id) == []
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE discovery_reads SET library_hash = %s WHERE reflection_id = %s",
                    (library_hash(load()), reflection_id))
        conn.commit()
    assert len(discovery._labels(user_id)) == 1
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE occasion_sources SET source_revision = source_revision + 1 "
                    "WHERE reflection_id = %s", (reflection_id,))
        conn.commit()
    assert discovery._labels(user_id) == []


def test_import_refuses_foreign_stale_and_unsupported_sources_without_writes(test_user, monkeypatch):
    user_id = test_user["id"]
    source_id = _entry(user_id)
    _, date = _revision(source_id)
    account = _stored_account(source_id, date)
    pattern_id = load()[0].id
    labels = _labels_for([account], pattern_id)
    db.update_reflection(source_id, content=PASSAGE + " ")
    stale = _revision(source_id)[0] - 1
    with pytest.raises(ValueError, match="changed"):
        discovery.load_reading(user_id, [account], labels,
                               source_revisions={source_id: stale},
                               extraction_version=EXTRACTION_VERSION, library_hash=library_hash(load()))
    changed = {**account, "response": "an unsupported paraphrase"}
    with pytest.raises(ValueError, match="unsupported"):
        _import(user_id, source_id, [changed], _labels_for([changed], pattern_id))
    staged = {**account, "citations": [
        {**account["citations"][0], "sourceType": "staged_import"}]}
    with pytest.raises(ValueError, match="not a reflection"):
        _import(user_id, source_id, [staged], _labels_for([staged], pattern_id))
    assert not _reading(user_id)
    other_id = db.create_user("discovery_foreign_source_" + str(source_id))
    try:
        with pytest.raises(ValueError, match="missing, ineligible, or changed"):
            discovery.load_reading(other_id, [account], labels,
                                   source_revisions={source_id: _revision(source_id)[0]},
                                   extraction_version=EXTRACTION_VERSION,
                                   library_hash=library_hash(load()))
    finally:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (other_id,))
            conn.commit()
    assert _completed(source_id) is None


def test_queue_dispatch_runs_discovery_without_regular_pipeline(monkeypatch):
    seen = []
    monkeypatch.setattr(discovery_worker, "process_reflection", lambda source_id: seen.append(source_id))
    monkeypatch.setattr(work_queue, "run_processing_pipeline", lambda *args: pytest.fail("wrong pipeline"))
    work_queue._run("discovery", 17)
    assert seen == [17]
