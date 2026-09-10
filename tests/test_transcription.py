"""Voice journals: transcribed, and the recording kept.

Mocked at the OpenAI SDK boundary — `openai.audio.transcriptions.create` — and
never at the seam under test, so the retry wrapper, the ffmpeg conversion and
the chunk-joining all really run.

The promise these protect is that the audio survives. A transcript is lossy and
cannot be un-made; if the original is gone, a garbled sentence is gone with it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent import transcription
from agent.config import settings
from agent.database import db
from agent.importing import store
from agent.importing.audio import run_transcription_job, store_recording

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed"
)


def _tone(path: Path, seconds: int = 2, hz: int = 440) -> Path:
    """A real audio file, so ffmpeg and ffprobe have something honest to read."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i",
         f"sine=frequency={hz}:duration={seconds}", str(path)],
        check=True, capture_output=True,
    )
    return path


@pytest.fixture
def audio_root(tmp_path, monkeypatch):
    """Keep every test's audio inside its own tmp_path."""
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path / "data"))
    return tmp_path


# --- storage ----------------------------------------------------------------

@needs_ffmpeg
def test_a_recording_is_stored_under_its_own_fingerprint(audio_root, test_user):
    src = _tone(audio_root / "memo.mp3")
    original = src.read_bytes()

    stored = store_recording(test_user["id"], src, "memo.mp3")

    assert stored["sha256"] in stored["rel_path"]
    assert stored["media_type"] == "audio/mpeg"
    assert stored["duration_seconds"] == pytest.approx(2.0, abs=0.2)

    from agent.importing.audio import resolve
    assert resolve(stored["rel_path"]).read_bytes() == original, (
        "the bytes the owner gave us are what is kept"
    )


@needs_ffmpeg
def test_the_same_recording_twice_is_stored_once(audio_root, test_user):
    a = store_recording(test_user["id"], _tone(audio_root / "one.mp3"), "one.mp3")
    b = store_recording(test_user["id"], _tone(audio_root / "two.mp3"), "two.mp3")
    assert a["rel_path"] == b["rel_path"], "content addressing de-duplicates for free"


def test_a_stored_path_cannot_point_outside_the_audio_directory(audio_root):
    from agent.importing.audio import resolve

    with pytest.raises(ValueError, match="outside"):
        resolve("../../etc/passwd")


# --- transcription ----------------------------------------------------------

@needs_ffmpeg
def test_the_configured_model_is_what_gets_called(audio_root, monkeypatch):
    seen = {}

    def fake(model=None, file=None, **kw):
        seen["model"] = model
        seen["name"] = Path(file.name).name
        return "the words that were spoken"

    monkeypatch.setattr("agent.transcription.openai.audio.transcriptions.create", fake)
    result = transcription.transcribe(_tone(audio_root / "memo.m4a"))

    assert result.text == "the words that were spoken"
    assert seen["model"] == settings.TRANSCRIPTION_MODEL
    assert seen["name"].endswith(".mp3"), (
        "the converted copy is sent, not the original — speech needs neither "
        "stereo nor 48 kHz, and the conversion is what keeps most files under "
        "the upload limit"
    )


@needs_ffmpeg
def test_the_original_survives_transcription_untouched(audio_root, monkeypatch):
    monkeypatch.setattr(
        "agent.transcription.openai.audio.transcriptions.create",
        lambda **kw: "words",
    )
    src = _tone(audio_root / "keep.mp3")
    before = src.read_bytes()

    transcription.transcribe(src)

    assert src.exists() and src.read_bytes() == before
    assert not (src.parent / ".transcode").exists(), "working copies are cleaned up"


@needs_ffmpeg
def test_a_long_recording_is_split_and_the_pieces_joined_in_order(audio_root, monkeypatch):
    monkeypatch.setattr(transcription, "CHUNK_SECONDS", 2)
    monkeypatch.setattr(transcription, "CHUNK_SLACK_SECONDS", 1)

    order = []

    def fake(model=None, file=None, **kw):
        order.append(Path(file.name).name)
        return f"piece {len(order)}"

    monkeypatch.setattr("agent.transcription.openai.audio.transcriptions.create", fake)
    result = transcription.transcribe(_tone(audio_root / "long.mp3", seconds=7))

    assert result.chunk_count > 1, "a recording past the chunk length must be split"
    assert order == sorted(order), "pieces must be sent in the order they were spoken"
    assert result.text == "\n\n".join(f"piece {i + 1}" for i in range(len(order)))


def test_a_missing_ffmpeg_is_a_clear_message(audio_root, monkeypatch):
    monkeypatch.setattr("agent.transcription.shutil.which", lambda name: None)
    with pytest.raises(transcription.TranscriptionUnavailable, match="ffmpeg is not installed"):
        transcription.normalise(audio_root / "nope.mp3", audio_root / "work")


# --- the queue job ----------------------------------------------------------

@pytest.fixture
def staged_recording(audio_root, test_user, monkeypatch):
    """A staged audio entry, as the upload endpoint would leave one."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    from agent.importing.audio import stage_recording

    batch_id = store.create_batch(test_user["id"], "audio", "memo.mp3", None)
    src = _tone(audio_root / "memo.mp3")
    staged = stage_recording(test_user["id"], batch_id, src, "memo.mp3",
                             recorded_at="2024-03-01T09:00:00Z")
    return {"batch_id": batch_id, **staged}


def test_a_transcript_fills_the_staged_entry(staged_recording, test_user, monkeypatch):
    monkeypatch.setattr(
        "agent.transcription.openai.audio.transcriptions.create",
        lambda **kw: "Woke up thinking about the same thing again.",
    )
    run_transcription_job(staged_recording["item_id"])

    item = store.get_item(staged_recording["item_id"], test_user["id"])
    assert item["content"] == "Woke up thinking about the same thing again."
    assert item["content_hash"], "the transcript is hashed so a re-upload is recognised"
    assert item["status"] == "staged", "it still awaits review like any other entry"
    assert str(item["entry_date"]) == "2024-03-01"


def test_a_provider_failure_keeps_the_audio_and_raises(staged_recording, test_user, monkeypatch):
    """The queue must retry rather than the recording being lost. The audio is
    already stored by the time this runs, so nothing the owner gave us is at
    risk either way."""
    def boom(**kw):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("agent.transcription.openai.audio.transcriptions.create", boom)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        run_transcription_job(staged_recording["item_id"])

    from agent.importing.audio import resolve
    assert resolve(staged_recording["rel_path"]).exists(), "the recording survives"

    item = store.get_item(staged_recording["item_id"], test_user["id"])
    assert item["content"] == "", "no half-written transcript"

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reflections WHERE user_id = %s;", (test_user["id"],))
        assert cur.fetchone()[0] == 0, "and nothing became an entry"


def test_a_silent_recording_is_reported_rather_than_retried_forever(
    staged_recording, test_user, monkeypatch
):
    monkeypatch.setattr(
        "agent.transcription.openai.audio.transcriptions.create", lambda **kw: "   "
    )
    run_transcription_job(staged_recording["item_id"])

    item = store.get_item(staged_recording["item_id"], test_user["id"])
    assert item["status"] == "failed"
    assert "heard" in (item["error"] or ""), "the reason has to be legible"


@needs_ffmpeg
def test_a_browser_recording_learns_its_own_duration(audio_root, test_user):
    """MediaRecorder writes webm as a live stream with no duration in the
    header, so `<audio>` shows no length and cannot seek. Remuxing with -c copy
    fixes the container without touching a single audio sample."""
    src = audio_root / "recording.webm"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:a", "libopus", "-f", "webm", str(src)],
        check=True, capture_output=True,
    )

    stored = store_recording(test_user["id"], src, "recording.webm")

    assert stored["duration_seconds"] == pytest.approx(2.0, abs=0.3), (
        "a saved recording must know how long it is, or playback cannot seek"
    )
    assert stored["rel_path"].endswith(".webm")
