"""The ingest queue: work survives a provider outage instead of being lost.

Before this, embedding ran inside the request and its failure was caught and
logged. An entry written while OpenAI was down was stored and never became
evidence — visible in the journal, invisible to every engine, with nothing to
say the two disagreed and nothing that would ever go back for it.

These tests are about that guarantee, not about the plumbing.
"""


from agent.database import db
from agent import work_queue
from agent.trackers.reflections import ReflectionService


def _queue_rows(user_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT source_type, source_id, attempts, last_error
               FROM processing_queue WHERE user_id = %s ORDER BY id;""",
            (user_id,),
        )
        return cur.fetchall()


def _embedding_count(source_type, source_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM embeddings WHERE source_type=%s AND source_id=%s;",
            (source_type, source_id),
        )
        return cur.fetchone()[0]


def _make_due_now(user_id):
    """Stand in for the backoff interval elapsing."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE processing_queue SET next_attempt_at = NOW() WHERE user_id = %s;",
            (user_id,),
        )
        conn.commit()


def test_a_write_returns_before_the_embedding_happens(test_user, mock_pipeline_logic):
    """The entry is stored and acknowledged; analysis is queued, not inline."""
    user_id = test_user["id"]
    reflection_id = ReflectionService(user_id).create_reflection(
        content="Work Stress today", energy_level=4
    )

    assert _embedding_count("reflection", reflection_id) == 0, (
        "embedding must not happen inside the write"
    )
    assert _queue_rows(user_id) == [("reflection", reflection_id, 0, None)]


def test_an_entry_written_during_an_outage_becomes_evidence_when_it_clears(
    test_user, mock_pipeline_logic, monkeypatch
):
    """The whole point of the queue, end to end."""
    user_id = test_user["id"]

    # The provider is down.
    def down(text, model=None):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("agent.pipeline.generate_embedding", down)

    reflection_id = ReflectionService(user_id).create_reflection(
        content="Work Stress during the outage", energy_level=4
    )
    succeeded, failed = work_queue.process_due()

    assert (succeeded, failed) == (0, 1)
    assert _embedding_count("reflection", reflection_id) == 0
    rows = _queue_rows(user_id)
    assert len(rows) == 1, "the item must still be queued, not dropped"
    assert rows[0][2] == 1, "the attempt must be recorded"
    assert "provider unavailable" in rows[0][3], "the failure must be legible"

    # The entry itself was never at risk.
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT content FROM reflections WHERE id = %s;", (reflection_id,))
        assert cur.fetchone()[0] == "Work Stress during the outage"

    # The provider comes back and the backoff elapses.
    monkeypatch.undo()
    monkeypatch.setattr("agent.pipeline.generate_embedding", lambda t, model=None: [0.1] * 1536)
    _make_due_now(user_id)

    assert work_queue.drain() == 1
    assert _embedding_count("reflection", reflection_id) == 1, (
        "work written during the outage must become evidence once it clears"
    )
    assert _queue_rows(user_id) == [], "completed work must leave the queue"


def test_a_failing_item_does_not_block_the_rest(test_user, monkeypatch):
    """One poisoned entry must not stop everything written after it."""
    user_id = test_user["id"]
    svc = ReflectionService(user_id)
    bad = svc.create_reflection(content="POISON entry", energy_level=4)
    good = svc.create_reflection(content="ordinary entry", energy_level=4)

    def selective(text, model=None):
        if "POISON" in text:
            raise RuntimeError("cannot embed this one")
        return [0.2] * 1536

    monkeypatch.setattr("agent.pipeline.generate_embedding", selective)
    monkeypatch.setattr(
        "agent.persistence.PersistenceEngine._generate_theme_summary", lambda s, e: "T"
    )

    succeeded, failed = work_queue.process_due()

    assert (succeeded, failed) == (1, 1)
    assert _embedding_count("reflection", good) == 1
    assert _embedding_count("reflection", bad) == 0
    assert [r[1] for r in _queue_rows(user_id)] == [bad]


def test_retries_back_off_and_then_park(test_user, mock_pipeline_logic, monkeypatch):
    """Backoff widens, and an exhausted item is kept and visible rather than
    retried forever or deleted."""
    user_id = test_user["id"]
    monkeypatch.setattr(
        "agent.pipeline.generate_embedding",
        lambda t, model=None: (_ for _ in ()).throw(RuntimeError("still down")),
    )
    ReflectionService(user_id).create_reflection(content="never embeds", energy_level=4)

    for expected_attempts in range(1, work_queue.MAX_ATTEMPTS + 1):
        _make_due_now(user_id)
        work_queue.process_due()
        assert _queue_rows(user_id)[0][2] == expected_attempts

    # Exhausted: still present, still explains itself, no longer claimed.
    rows = _queue_rows(user_id)
    assert len(rows) == 1, "an exhausted item must not be silently deleted"
    assert "still down" in rows[0][3]

    _make_due_now(user_id)
    assert work_queue.process_due() == (0, 0), (
        "an exhausted item must stop consuming attempts"
    )
    assert work_queue.pending(user_id)[0]["exhausted"] is True


def test_enqueueing_the_same_item_twice_queues_it_once(test_user):
    user_id = test_user["id"]
    work_queue.enqueue("reflection", 4242, user_id)
    work_queue.enqueue("reflection", 4242, user_id)
    assert len(_queue_rows(user_id)) == 1


def test_the_worker_thread_drains_without_being_asked(test_user, mock_pipeline_logic):
    """The background worker is what makes this durable in production; a queue
    nothing runs is just a slower way to lose the work."""
    user_id = test_user["id"]
    reflection_id = ReflectionService(user_id).create_reflection(
        content="Work Stress for the worker", energy_level=4
    )

    worker = work_queue.QueueWorker(poll_seconds=1)
    worker.start()
    try:
        deadline = __import__("time").time() + 15
        while __import__("time").time() < deadline:
            if _embedding_count("reflection", reflection_id) == 1:
                break
            __import__("time").sleep(0.2)
    finally:
        worker.stop()

    assert _embedding_count("reflection", reflection_id) == 1, (
        "the worker must process queued work with no explicit drain"
    )
    assert _queue_rows(user_id) == []
