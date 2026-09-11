"""A file's saved time: kept, offered, never applied on its own.

ADR-0013 rules out dating an entry by its file's modification time, because a
note is edited after the day it describes and a copy resets the time. The owner
asked for it anyway, for notes that carry no date at all, as a guess they
choose and that stays marked as one. These tests pin the difference between
offering and applying, and the situations where a file time is worse than
nothing: a time the server made itself, a day an export stamped on every file,
and one time shared by many entries.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from agent.importing.adapters import ParsedEntry
from agent.importing.service import FILE_TIMES, _usable_file_times
from iris_api import app, get_current_user_id

WORDS = "Slept badly again but got the deployment finished before lunch, which helped."


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _zip(members: dict[str, tuple[str, tuple]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, (text, saved) in members.items():
            zf.writestr(zipfile.ZipInfo(name, date_time=saved), text)
    return buf.getvalue()


def _upload(client, data: bytes, name: str = "notes.zip", **form) -> dict:
    r = client.post("/api/import/batches",
                    files={"file": (name, data, "application/octet-stream")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


def _entries(client, batch: dict) -> list[dict]:
    return client.get(f"/api/import/batches/{batch['id']}/entries").json()["entries"]


def _vault() -> dict[str, tuple[str, tuple]]:
    """Three notes with nothing in them that says when, saved on three days —
    the shape of the owner's Obsidian journal."""
    return {
        "Journal/Rough week.md": (WORDS + " One.", (2026, 3, 7, 21, 40, 0)),
        "Journal/Better.md": (WORDS + " Two.", (2026, 3, 11, 9, 5, 0)),
        # Late evening, local: must stay on its own day, not slide into the next.
        "Journal/Gym again.md": (WORDS + " Three.", (2026, 4, 2, 23, 30, 0)),
    }


def test_a_file_time_is_offered_not_applied(client):
    batch = _upload(client, _zip(_vault()))

    assert batch["counts"]["needsDate"] == 3, "a file time must never date an entry by itself"
    entries = _entries(client, batch)
    assert all(e["occurredOn"] is None for e in entries)
    assert sorted(e["fileModifiedOn"] for e in entries) == \
        ["2026-03-07", "2026-03-11", "2026-04-02"]


def test_choosing_it_dates_the_entry_as_a_guess(client):
    batch = _upload(client, _zip(_vault()))
    ids = [int(e["id"]) for e in _entries(client, batch)]

    r = client.post("/api/import/entries/bulk", json={"ids": ids, "op": "use_file_date"})
    assert r.json() == {"updated": 3}

    entries = _entries(client, batch)
    assert sorted(e["occurredOn"] for e in entries) == ["2026-03-07", "2026-03-11", "2026-04-02"]
    assert {(e["dateSource"], e["dateConfidence"]) for e in entries} == {("mtime", "probable")}, \
        "a file time is never certain"
    # Probable is committable: the owner chose it, and review keeps showing it as a guess.
    assert client.get(f"/api/import/batches/{batch['id']}").json()["counts"]["needsDate"] == 0


def test_it_never_replaces_a_date_the_writing_gave(client):
    members = {"2024-03-01.md": (WORDS, (2026, 3, 7, 21, 40, 0)),
               "2024-03-02.md": (WORDS + " Again.", (2026, 3, 8, 9, 0, 0))}
    batch = _upload(client, _zip(members))
    ids = [int(e["id"]) for e in _entries(client, batch)]

    r = client.post("/api/import/entries/bulk", json={"ids": ids, "op": "use_file_date"})

    assert r.json() == {"updated": 0}
    assert sorted(e["occurredOn"] for e in _entries(client, batch)) == ["2024-03-01", "2024-03-02"]


def test_a_day_many_files_share_is_a_copy_not_a_writing_day(client):
    """An export or a copy stamps every file with the same moment. Offering it
    would pile the whole journal onto one day, as the Elara `date` field did."""
    stamp = (2025, 10, 18, 8, 35, 54)
    members = {f"notes/Page {i}.md": (f"{WORDS} Page {i}.", stamp) for i in range(5)}
    members["notes/Other.md"] = (WORDS + " Other.", (2025, 6, 1, 12, 0, 0))
    batch = _upload(client, _zip(members))
    entries = {e["sourceName"]: e for e in _entries(client, batch)}

    stamped = [e for name, e in entries.items() if "Page" in name]
    assert len(stamped) == 5
    assert all(e["fileModifiedOn"] is None for e in stamped)
    assert all(any("copied or exported" in w for w in e["warnings"]) for e in stamped)
    assert entries["notes/Other.md"]["fileModifiedOn"] == "2025-06-01"


def test_a_time_shared_by_several_entries_dates_none_of_them(tmp_path):
    """A time dates a file. A file holding forty entries has one time between
    them, and it is not the day any particular one of them was written."""
    (tmp_path / FILE_TIMES).write_text(json.dumps({"journal.md": time.time() - 40 * 86400}))
    entries = [ParsedEntry(content=WORDS, source_path="journal.md"),
               ParsedEntry(content=WORDS + " Again.", source_path="journal.md")]

    assert _usable_file_times(tmp_path, entries) == ({}, {})


def test_the_servers_own_copy_time_is_never_offered(client):
    """Without the browser's reading, the only time on a single uploaded file is
    the moment it arrived: 'dated today', one step removed."""
    batch = _upload(client, WORDS.encode(), name="Rough week.md")
    entry = _entries(client, batch)[0]
    assert entry["occurredOn"] is None and entry["fileModifiedOn"] is None


def test_the_browsers_reading_is_used_for_a_single_file(client):
    saved = datetime(2026, 3, 7, 21, 40)
    batch = _upload(client, WORDS.encode(), name="Rough week.md",
                    lastModified=str(int(saved.timestamp() * 1000)))
    assert _entries(client, batch)[0]["fileModifiedOn"] == "2026-03-07"


def test_the_zip_formats_empty_time_is_not_a_date(client):
    members = {"a.md": (WORDS, (1980, 1, 1, 0, 0, 0)),
               "b.md": (WORDS + " Again.", (1980, 1, 1, 0, 0, 0))}
    batch = _upload(client, _zip(members))
    assert all(e["fileModifiedOn"] is None for e in _entries(client, batch))


def test_a_reparse_keeps_the_file_times(client):
    batch = _upload(client, _zip(_vault()))
    r = client.post(f"/api/import/batches/{batch['id']}/reparse", json={"adapter": "dated_files"})
    assert r.status_code == 200, r.text
    assert all(e["fileModifiedOn"] for e in _entries(client, batch))
