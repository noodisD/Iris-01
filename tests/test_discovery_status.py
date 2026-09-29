"""Discovery status and explicit archive refresh are owner-scoped and idempotent."""

from fastapi.testclient import TestClient

from agent.database import db
from agent.work_queue import MAX_ATTEMPTS, process_due
from iris_api import app, get_current_user_id


def _client(user_id):
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


def test_empty_success_is_current_and_excluded_entries_never_read(test_user):
    owner = test_user["id"]
    db.create_reflection(owner, "I asked for help with the map and found the route.")
    db.create_reflection(owner, "", energy_level=5)
    db.create_reflection(owner, "Copied setup notes, not my experience.", evidence_eligible=False)
    client = _client(owner)
    try:
        before = client.get("/api/discovery/status").json()
        assert (before["eligibleEntries"], before["pendingEntries"],
                before["excludedEntries"], before["unreadEntries"]) == (1, 1, 2, 0)
        assert before["currentEntries"] == 0
        process_due(limit=20)  # offline reader returns a valid empty episode list
        after = client.get("/api/discovery/status").json()
        assert (after["currentEntries"], after["pendingEntries"],
                after["unreadEntries"], after["omittedAccounts"]) == (1, 0, 0, 0)
        assert after["lastCompletedAt"] is not None
        assert client.post("/api/discovery/refresh", json={"scope": "unread"}).json() == {
            "queuedEntries": 0}
    finally:
        app.dependency_overrides.clear()


def test_explicit_unread_and_failed_refresh_are_idempotent_and_owner_scoped(test_user):
    owner = test_user["id"]
    entry = db.create_reflection(owner, "I stopped by the workshop and waited for the door.")
    other = db.create_user("discovery-status-other")
    db.create_reflection(other, "I went to the station and asked for a map.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM processing_queue WHERE source_type = 'discovery' AND source_id = %s", (entry,))
        conn.commit()
    client = _client(owner)
    try:
        unread = client.get("/api/discovery/status").json()
        assert (unread["eligibleEntries"], unread["unreadEntries"],
                unread["pendingEntries"], unread["estimatedRequests"]) == (1, 1, 0, 7)
        assert "Approximate" in unread["estimate"]
        assert client.post("/api/discovery/refresh", json={"scope": "unread"}).status_code == 202
        assert client.post("/api/discovery/refresh", json={"scope": "unread"}).json() == {
            "queuedEntries": 0}
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE processing_queue SET attempts = %s, last_error = 'unavailable'
                            WHERE source_type = 'discovery' AND source_id = %s""",
                        (MAX_ATTEMPTS, entry))
            conn.commit()
        parked = client.get("/api/discovery/status").json()
        assert (parked["failedEntries"], parked["pendingEntries"], parked["unreadEntries"]) == (1, 0, 0)
        assert client.post("/api/discovery/refresh", json={"scope": "failed"}).json() == {
            "queuedEntries": 1}
        assert client.post("/api/discovery/refresh", json={"scope": "failed"}).json() == {
            "queuedEntries": 0}
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT attempts, last_error FROM processing_queue
                            WHERE source_type = 'discovery' AND source_id = %s""", (entry,))
            assert cur.fetchone() == (0, None)
    finally:
        app.dependency_overrides.clear()
        db.delete_reflection(entry)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (other,))
            conn.commit()
