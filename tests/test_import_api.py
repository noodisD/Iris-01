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


# --- findings from the 2026-09-11 review, each reproduced before it was fixed ---

import shutil
import subprocess

from agent.database import db as _db

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


def _tone_bytes(tmp_path) -> bytes:
    path = tmp_path / "memo.mp3"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", str(path)],
                   check=True, capture_output=True)
    return path.read_bytes()


def _upload_audio(client, data: bytes, **form):
    return client.post("/api/import/audio",
                       files={"file": ("memo.mp3", data, "audio/mpeg")}, data=form)


@needs_ffmpeg
def test_a_recording_cannot_be_committed_before_its_transcript(client, tmp_path, monkeypatch,
                                                              process_queue):
    """Committing used to be allowed, and produced a failed item reading
    "Reflection content cannot be empty" — a message about nothing the owner
    did or could fix. The answer is to wait, so the gate says that."""
    r = _upload_audio(client, _tone_bytes(tmp_path), recordedAt="2026-02-14T21:30:00Z")
    batch_id = r.json()["batchId"]

    batch = client.get(f"/api/import/batches/{batch_id}").json()
    assert batch["counts"]["awaitingTranscript"] == 1
    r = client.post(f"/api/import/batches/{batch_id}/commit")
    assert r.status_code == 409
    assert "being transcribed" in r.json()["detail"]

    monkeypatch.setattr("agent.transcription.openai.audio.transcriptions.create",
                        lambda **kw: "Spoken words, now written down.")
    process_queue()
    assert client.post(f"/api/import/batches/{batch_id}/commit").json()["committed"] == 1


def test_a_batch_that_could_not_import_everything_does_not_report_success(client, test_user):
    """'committed' used to mean "the commit ran". A batch whose entries failed
    still said it had succeeded."""
    batch = _upload(client, _dated_export(["2024-03-01", "2024-03-02"]))
    entries = client.get(f"/api/import/batches/{batch['id']}/entries").json()["entries"]
    # Blank the content of one text entry; create_reflection rejects it for real.
    from agent.importing import store
    store.update_item(int(entries[0]["id"]), test_user["id"], content="   ")

    result = client.post(f"/api/import/batches/{batch['id']}/commit").json()
    assert result == {"committed": 1, "duplicates": 0, "failed": 1, "excluded": 0}

    after = client.get(f"/api/import/batches/{batch['id']}").json()
    assert after["status"] == "failed"
    assert "1 of 2" in after["error"]


@needs_ffmpeg
@pytest.mark.parametrize("scenario", ["someone_else", "text_import", "already_committed"])
def test_a_recording_can_only_join_an_open_audio_import_you_own(client, test_user, tmp_path,
                                                               scenario):
    """A batch id from the client is a claim. It was used unchecked."""
    from agent.importing import store

    if scenario == "someone_else":
        with _db.connection() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO users (username, password_hash) "
                        "VALUES ('someone_else', 'x') RETURNING id;")
            other = cur.fetchone()[0]
            conn.commit()
        target = store.create_batch(other, "audio", "theirs.mp3", None)
    elif scenario == "text_import":
        target = int(_upload(client, _dated_export(["2024-03-01"]))["id"])
    else:
        target = store.create_batch(test_user["id"], "audio", "old.mp3", None)
        store.update_batch(target, status="committed")

    r = _upload_audio(client, _tone_bytes(tmp_path), batchId=str(target))
    assert r.status_code == 400, f"{scenario}: {r.status_code} {r.text}"

    if scenario == "someone_else":
        with _db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM import_items WHERE batch_id = %s;", (target,))
            assert cur.fetchone()[0] == 0, "nothing may be appended to another account's import"
            cur.execute("DELETE FROM users WHERE username = 'someone_else';")
            conn.commit()


@needs_ffmpeg
def test_undoing_a_voice_import_deletes_the_recording(client, tmp_path, monkeypatch, process_queue):
    """Undo removed the entries and kept the audio — the most personal part of
    what was imported."""
    from agent.importing.audio import resolve

    r = _upload_audio(client, _tone_bytes(tmp_path), recordedAt="2026-02-14T21:30:00Z")
    batch_id = r.json()["batchId"]
    monkeypatch.setattr("agent.transcription.openai.audio.transcriptions.create",
                        lambda **kw: "Spoken words.")
    process_queue()
    client.post(f"/api/import/batches/{batch_id}/commit")

    with _db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT audio_path FROM reflections WHERE source = 'voice';")
        stored = resolve(cur.fetchone()[0])
    assert stored.exists()

    body = client.delete(f"/api/import/batches/{batch_id}?withReflections=true").json()
    assert body["recordings_removed"] == 1
    assert not stored.exists(), "undo must not keep the recording"
