"""Importing, end to end: upload, review, commit, and become evidence.

The test that matters here is the last one. An import is not finished when rows
appear in `reflections` — it is finished when those entries have been embedded,
offered to the analytical engines, and recorded as occurrences carrying the date
they were originally written. Everything else in this file protects that.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from iris_api import app, get_current_user_id

ENTRY = ("Work pressure again this week. Another late night finishing the deck "
         "before the review, and I skipped the gym for the third time running.")


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _zip_bytes(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _upload(client, members: dict[str, str], name: str = "export.zip") -> dict:
    r = client.post(
        "/api/import/batches",
        files={"file": (name, _zip_bytes(members), "application/zip")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _dated_export(days: list[str]) -> dict[str, str]:
    return {f"{d}.md": f"{ENTRY} Written on {d}." for d in days}


# --- staging ----------------------------------------------------------------

def test_an_upload_is_read_and_held_for_review(client):
    batch = _upload(client, _dated_export(["2024-03-01", "2024-03-02", "2024-03-03"]))

    assert batch["status"] == "needs_review", "nothing is written before review"
    assert batch["adapter"] == "dated_files"
    assert batch["counts"]["total"] == 3
    assert batch["counts"]["needsDate"] == 0
    assert batch["counts"]["earliest"] == "2024-03-01"

    entries = client.get(f"/api/import/batches/{batch['id']}/entries").json()["entries"]
    assert [e["occurredOn"] for e in entries] == ["2024-03-01", "2024-03-02", "2024-03-03"]
    assert all(e["dateConfidence"] == "certain" for e in entries)


def test_nothing_reaches_reflections_until_it_is_committed(client, test_user):
    _upload(client, _dated_export(["2024-03-01"]))
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reflections WHERE user_id = %s;", (test_user["id"],))
        assert cur.fetchone()[0] == 0


def test_the_detected_format_can_be_overruled(client):
    batch = _upload(client, _dated_export(["2024-03-01", "2024-03-02"]))
    r = client.post(f"/api/import/batches/{batch['id']}/reparse",
                    json={"adapter": "plain_files"})
    assert r.status_code == 200, r.text
    assert r.json()["adapter"] == "plain_files"


# --- the rule that protects every analytical window -------------------------

def test_an_undated_entry_blocks_the_commit(client, test_user):
    batch = _upload(client, {"some thoughts.md": ENTRY})
    assert batch["counts"]["needsDate"] == 1

    r = client.post(f"/api/import/batches/{batch['id']}/commit")
    assert r.status_code == 409, "an unknown date must not be guessed at commit"
    assert "no date" in r.json()["detail"]

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reflections WHERE user_id = %s;", (test_user["id"],))
        assert cur.fetchone()[0] == 0, "a refused commit must write nothing"


def test_setting_the_date_unblocks_it(client):
    batch = _upload(client, {"some thoughts.md": ENTRY})
    entry = client.get(f"/api/import/batches/{batch['id']}/entries").json()["entries"][0]

    r = client.patch(f"/api/import/entries/{entry['id']}", json={"occurredOn": "2023-11-04"})
    assert r.status_code == 200, r.text
    assert r.json()["occurredOn"] == "2023-11-04"
    assert r.json()["dateConfidence"] == "certain"

    assert client.post(f"/api/import/batches/{batch['id']}/commit").json()["committed"] == 1


def test_an_undated_entry_can_be_excluded_instead(client):
    batch = _upload(client, {"undated.md": ENTRY, "2024-03-01.md": ENTRY + " Dated."})
    entries = client.get(f"/api/import/batches/{batch['id']}/entries").json()["entries"]
    undated = next(e for e in entries if e["occurredOn"] is None)

    client.patch(f"/api/import/entries/{undated['id']}", json={"status": "excluded"})
    result = client.post(f"/api/import/batches/{batch['id']}/commit").json()
    assert result["committed"] == 1
    assert result["excluded"] == 1


# --- committing -------------------------------------------------------------

def test_entries_keep_the_date_they_were_written(client, test_user):
    """The whole point. An entry written in 2019 must land in 2019, not today."""
    batch = _upload(client, _dated_export(["2019-03-04", "2021-07-15"]))
    assert client.post(f"/api/import/batches/{batch['id']}/commit").json()["committed"] == 2

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT reflection_date, source FROM reflections WHERE user_id = %s ORDER BY reflection_date;",
            (test_user["id"],),
        )
        rows = cur.fetchall()
    assert [r[0] for r in rows] == [date(2019, 3, 4), date(2021, 7, 15)]
    assert all(r[1] == "import" for r in rows), "provenance is recorded"


def test_importing_the_same_export_twice_does_not_double_the_journal(client, test_user):
    members = _dated_export(["2024-03-01", "2024-03-02"])
    first = _upload(client, members)
    assert client.post(f"/api/import/batches/{first['id']}/commit").json()["committed"] == 2

    second = _upload(client, members)
    assert second["counts"]["duplicate"] == 2, "re-imported entries are recognised"
    assert client.post(f"/api/import/batches/{second['id']}/commit").json()["committed"] == 0

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reflections WHERE user_id = %s;", (test_user["id"],))
        assert cur.fetchone()[0] == 2


def test_the_same_words_on_a_different_day_are_a_second_entry(client, test_user):
    """De-duplication must not swallow a genuine repeat. Someone who writes the
    same sentence on Monday and Thursday wrote two entries."""
    batch = _upload(client, {"2024-03-01.md": ENTRY, "2024-03-08.md": ENTRY})
    assert batch["counts"]["duplicate"] == 0
    assert client.post(f"/api/import/batches/{batch['id']}/commit").json()["committed"] == 2


# --- undo -------------------------------------------------------------------

def test_a_committed_import_can_be_undone(client, test_user, process_queue):
    batch = _upload(client, _dated_export(["2024-03-01", "2024-03-02"]))
    client.post(f"/api/import/batches/{batch['id']}/commit")
    process_queue()

    r = client.delete(f"/api/import/batches/{batch['id']}?withReflections=true")
    assert r.status_code == 200, r.text
    assert r.json()["reflections_removed"] == 2

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reflections WHERE user_id = %s;", (test_user["id"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM embeddings WHERE source_type = 'reflection';")
        assert cur.fetchone()[0] == 0, "embeddings go with the entries"
        cur.execute("SELECT count(*) FROM theme_occurrences WHERE source_type = 'reflection';")
        assert cur.fetchone()[0] == 0, "and so does the evidence built on them"


# --- the requirement: imported writing becomes evidence ---------------------

def test_imported_entries_are_embedded_and_become_evidence(client, test_user, process_queue):
    """An import is not finished when rows appear in `reflections`.

    It is finished when those entries have gone through the same pipeline as
    anything typed into the app — embedded, offered to the engines, and recorded
    as occurrences dated when they were written rather than when they were
    imported.
    """
    user_id = test_user["id"]
    # Six entries about one recurring subject, spread across a fortnight last
    # year, so the theme they form is dated then and not now.
    start = date.today() - timedelta(days=400)
    members = {
        f"{(start + timedelta(days=i * 2)).isoformat()}.md":
            f"Work pressure keeps building. Another late night on the deck, "
            f"and I skipped the gym again. Day {i}."
        for i in range(6)
    }
    batch = _upload(client, members)
    assert client.post(f"/api/import/batches/{batch['id']}/commit").json()["committed"] == 6

    # The commit enqueues; this is where the worker's work happens.
    process_queue()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM embeddings e JOIN reflections r ON r.id = e.source_id
               WHERE e.source_type = 'reflection' AND r.user_id = %s;""",
            (user_id,),
        )
        assert cur.fetchone()[0] == 6, "every imported entry must be embedded"

        cur.execute(
            "SELECT processing_status, count(*) FROM reflections WHERE user_id = %s GROUP BY 1;",
            (user_id,),
        )
        assert dict(cur.fetchall()) == {"complete": 6}

        cur.execute("SELECT count(*) FROM themes WHERE user_id = %s;", (user_id,))
        assert cur.fetchone()[0] >= 1, (
            "six related entries must form a theme — the analytical spine has to "
            "see imported writing exactly as it sees anything else"
        )

        cur.execute(
            """SELECT MIN(o.occurred_at)::date, MAX(o.occurred_at)::date
               FROM theme_occurrences o JOIN themes t ON t.id = o.theme_id
               WHERE t.user_id = %s;""",
            (user_id,),
        )
        earliest, latest = cur.fetchone()

    assert earliest == start, (
        f"the evidence is dated when it was written, not when it was imported "
        f"(got {earliest}, expected {start})"
    )
    assert latest < date.today() - timedelta(days=300), (
        "a backfilled archive must not register as activity happening now"
    )
