"""Speakers sorted out from the recording, only on the owner's click (ADR-0028).

No audio is read and nothing is sent: the transcriber's reply is scripted.
Every line of every transcript below is invented.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent import session_voices, sessions
from agent.database import db
from agent.session_imports import SessionImportError, SessionImports
from agent.session_voices import Heard
from iris_api import app, get_current_user_id

TRANSCRIPT = """**[00:00:00] Ann:**
I kept postponing the call to my landlord because I expected an argument about the heating.

**[00:00:10] Counsellor:**
What happened when you finally called him about it, in the end?

**[00:00:20] Speaker unsure:**
He agreed to fix the heating straight away.

**[00:00:30] Ann:**
And I felt silly for waiting so long, to be honest with you.

**[00:00:40] Speaker unsure:**
So the waiting cost more than the call did.

**[00:00:50] Speaker unsure:**
Mhm.
"""

NAMES = ("Ann", "Counsellor")


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _found():
    return sessions.segments(TRANSCRIPT)[0]


# --- the arithmetic --------------------------------------------------------------

def test_relabelling_changes_only_the_labels():
    labels = ["Ann", "Counsellor", "Ann", "Ann", "Counsellor", "Speaker unsure"]
    out = sessions.relabel_segments(TRANSCRIPT, labels)
    assert [s.label for s in sessions.segments(out)[0]] == labels
    assert [s.text for s in sessions.segments(out)[0]] == [s.text for s in _found()]
    changed = [(before, after) for before, after in zip(TRANSCRIPT.splitlines(), out.splitlines())
               if before != after]
    assert changed == [("**[00:00:20] Speaker unsure:**", "**[00:00:20] Ann:**"),
                       ("**[00:00:40] Speaker unsure:**", "**[00:00:40] Counsellor:**")]
    with pytest.raises(ValueError):
        sessions.relabel_segments(TRANSCRIPT, labels[:-1])


def test_an_unsure_line_takes_the_voice_that_fills_it_and_a_contradicted_one_turns_unsure():
    heard = [Heard("Ann", 0, 10), Heard("Counsellor", 10, 19.5), Heard("Ann", 20, 30),
             Heard("Counsellor", 30, 40),   # the transcript says Ann; the voice says otherwise
             Heard("Ann", 40, 44), Heard("Counsellor", 44, 50),  # no voice holds 70%
             Heard("Counsellor", 50, 55)]
    labels, report = session_voices.relabel(_found(), heard, NAMES, "(unsure)")
    assert labels == ["Ann", "Counsellor", "Ann", "Ann (unsure)", "Speaker unsure", "Counsellor"]
    assert report["attributed"] == {"Ann": 1, "Counsellor": 1}
    assert (report["labelled"], report["agreed"], report["contradicted"], report["doubtful"]) == (3, 2, 1, 1)


def test_a_lettered_voice_heard_in_one_speakers_turns_is_that_speaker():
    heard = [Heard("A", 0, 10), Heard("A", 30, 40), Heard("B", 10, 20), Heard("C", 41, 42)]
    named = session_voices.name_unnamed(heard, _found(), NAMES)
    assert [h.speaker for h in named] == ["Ann", "Ann", "Counsellor", "C"]


# --- the pass ----------------------------------------------------------------------

def _staged_with_recording(user_id: int, tmp_path) -> tuple[SessionImports, int]:
    imports = SessionImports(user_id)
    import_id = int(imports.stage(TRANSCRIPT, "session.md")["id"])
    audio = tmp_path / "session.m4a"
    audio.write_bytes(b"not really audio")
    imports.keep_recording(import_id, audio, "session.m4a")
    return imports, import_id


@pytest.fixture
def recordings(tmp_path, monkeypatch):
    monkeypatch.setattr(session_voices, "recordings_root", lambda: tmp_path / "recordings")
    monkeypatch.setattr("agent.session_imports.recordings_root", lambda: tmp_path / "recordings")
    monkeypatch.setattr(session_voices, "_samples", lambda found, audio, workdir, names: ["a", "b"])
    monkeypatch.setattr(session_voices, "_parts", lambda audio, workdir: [(0.0, audio)])
    return tmp_path / "recordings"


def test_the_pass_relabels_keeps_the_old_labels_and_can_be_undone(test_user, tmp_path, recordings, monkeypatch):
    sent = []
    monkeypatch.setattr(session_voices, "_diarize", lambda parts, names, samples, language: sent.append(names) or [
        Heard("Ann", 0, 10), Heard("Counsellor", 10, 20), Heard("Ann", 20, 40),
        Heard("Counsellor", 40, 50), Heard("Counsellor", 50, 55)])
    imports, import_id = _staged_with_recording(test_user["id"], tmp_path)
    assert (recordings / f"{import_id}.m4a").exists()
    assert not sent, "keeping the recording sends nothing"

    imports.start_voices(import_id)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM processing_queue WHERE source_type = 'session_voices' AND source_id = %s;",
                    (import_id,))
        assert cur.fetchone()[0] == 1
    with pytest.raises(SessionImportError, match="being sorted out"):
        imports.commit(import_id)
    session_voices.run(import_id)

    done = imports.get(import_id)
    assert sent == [NAMES]
    assert done["voices"]["status"] == "done"
    assert {s["label"] for s in done["speakers"]} == {"Ann", "Counsellor"}
    assert done["voices"]["report"]["attributed"] == {"Ann": 1, "Counsellor": 2}

    undone = imports.undo_voices(import_id)
    assert undone["voices"]["status"] == "none"
    assert "Speaker unsure" in {s["label"] for s in undone["speakers"]}


def test_voices_that_do_not_match_the_transcript_change_nothing(test_user, tmp_path, recordings, monkeypatch):
    monkeypatch.setattr(session_voices, "_diarize", lambda *a: [
        Heard("Counsellor", 0, 10), Heard("Ann", 10, 20), Heard("Counsellor", 20, 40)])
    imports, import_id = _staged_with_recording(test_user["id"], tmp_path)
    imports.start_voices(import_id)
    session_voices.run(import_id)
    failed = imports.get(import_id)
    assert failed["voices"]["status"] == "failed"
    assert "nothing was changed" in failed["voices"]["error"]
    assert "Speaker unsure" in {s["label"] for s in failed["speakers"]}


def test_a_provider_failure_is_shown_and_not_retried(test_user, tmp_path, recordings, monkeypatch):
    def broken(*a):
        raise RuntimeError("provider down")
    monkeypatch.setattr(session_voices, "_diarize", broken)
    imports, import_id = _staged_with_recording(test_user["id"], tmp_path)
    imports.start_voices(import_id)
    session_voices.run(import_id)
    failed = imports.get(import_id)
    assert failed["voices"]["status"] == "failed"
    assert "provider down" not in failed["voices"]["error"]


def test_importing_drops_the_recording(test_user, tmp_path, recordings):
    imports, import_id = _staged_with_recording(test_user["id"], tmp_path)
    imports.update(import_id, {"startedAt": "2026-09-30T18:00"})
    imports.commit(import_id)
    assert not (recordings / f"{import_id}.m4a").exists()
    assert imports.get(import_id)["voices"]["hasRecording"] is False


def test_the_recording_routes(client, recordings):
    staged = client.post("/api/sessions/imports",
                         files={"file": ("session.md", TRANSCRIPT.encode(), "text/markdown")}).json()
    import_id = staged["id"]
    assert client.post(f"/api/sessions/imports/{import_id}/voices").status_code == 400, "no recording yet"
    refused = client.post(f"/api/sessions/imports/{import_id}/recording",
                          files={"file": ("notes.txt", b"x", "text/plain")})
    assert refused.status_code == 400
    kept = client.post(f"/api/sessions/imports/{import_id}/recording",
                       files={"file": ("session.mp3", b"not really audio", "audio/mpeg")})
    assert kept.status_code == 200 and kept.json()["voices"]["hasRecording"] is True
    started = client.post(f"/api/sessions/imports/{import_id}/voices")
    assert started.status_code == 200 and started.json()["voices"]["status"] == "queued"


def test_a_pass_cut_off_by_a_restart_can_be_tried_again(test_user, tmp_path, recordings):
    imports, import_id = _staged_with_recording(test_user["id"], tmp_path)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE session_imports SET voices_status = 'running',
                              updated_at = NOW() - interval '2 hours' WHERE id = %s;""", (import_id,))
        conn.commit()
    stale = imports.get(import_id)
    assert stale["voices"]["status"] == "failed" and "Try again" in stale["voices"]["error"]
    assert imports.start_voices(import_id)["voices"]["status"] == "queued"


# --- a recording with no transcript ----------------------------------------------

def test_a_transcript_is_built_with_known_voices_named_and_the_rest_unclear():
    heard = [Heard("Ann", 0, 5, "I kept postponing the call to my landlord."),
             Heard("A", 5, 7, "Mhm."),
             Heard("Counsellor", 7, 12, "What happened when you called?")]
    text = session_voices.transcript_from(heard, {"Ann": "Ann", "Counsellor": "Counsellor"}, "en")
    assert [s.label for s in sessions.segments(text)[0]] == ["Ann", "Speaker unclear", "Counsellor"]
    lettered = session_voices.transcript_from(heard, {}, "pl")
    assert [s.label for s in sessions.segments(lettered)[0]] == ["Mówca Ann", "Mówca A", "Mówca Counsellor"]


def test_a_recording_is_staged_transcribed_on_the_click_and_then_imported(test_user, tmp_path, recordings,
                                                                          monkeypatch):
    voices = tmp_path / "voices"
    monkeypatch.setattr(session_voices, "voices_root", lambda: voices)
    session_voices.save_voice("owner", "Ann", b"RIFFowner")
    session_voices.save_voice("therapist", "Counsellor", b"RIFFtherapist")
    sent = []
    monkeypatch.setattr(session_voices, "_diarize", lambda parts, names, samples, language: sent.append(
        (names, len(samples))) or [
        Heard("Ann", 0, 9, "I kept postponing the call to my landlord because I expected an argument."),
        Heard("Counsellor", 9, 15, "What happened when you finally called him about it?"),
        Heard("Ann", 15, 25, "He agreed to fix the heating straight away, and I felt silly.")])
    audio = tmp_path / "session.m4a"
    audio.write_bytes(b"not really audio")
    imports = SessionImports(test_user["id"])
    staged = imports.stage_recording(audio, "session.m4a")
    import_id = int(staged["id"])
    assert staged["needsTranscript"] and staged["voices"]["hasRecording"]
    assert "a transcript (transcribe the recording)" in staged["missing"]
    assert not sent, "staging sends nothing"
    with pytest.raises(SessionImportError):
        imports.commit(import_id)

    imports.start_voices(import_id)
    session_voices.run(import_id)
    done = imports.get(import_id)
    assert sent == [(("Ann", "Counsellor"), 2)]
    assert not done["needsTranscript"] and done["voices"]["report"]["transcribed"]
    assert (done["owner"], done["therapist"]) == ("Ann", "Counsellor")
    imports.update(import_id, {"startedAt": "2026-10-07T18:04"})
    assert imports.commit(import_id)["status"] == "imported"


def test_the_recording_upload_route(client, recordings):
    staged = client.post("/api/sessions/recordings", files={"file": ("s.m4a", b"not really audio", "audio/mp4")})
    assert staged.status_code == 200 and staged.json()["needsTranscript"]
    assert client.post("/api/sessions/recordings",
                       files={"file": ("s.txt", b"x", "text/plain")}).status_code == 400
