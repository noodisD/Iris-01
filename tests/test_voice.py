"""Talking with IRIS (ADR-0025): speech in and out around an ordinary chat turn.

The provider is replaced by doubles; nothing here is sent anywhere. Phrases are
invented and neutral.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agent import voice
from agent.config import settings
from iris_api import app, get_current_user_id

HEARD = "What should I plant along the north fence this spring?"


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def heard(monkeypatch, tmp_path):
    """The transcriber, replaced: it records the file it was given."""
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    calls: list[dict] = []

    def fake(path: Path, model: str, language: str | None = None) -> str:
        calls.append({"path": path, "existed": path.exists(), "model": model, "language": language})
        if getattr(fake, "fail", False):
            raise RuntimeError("provider down")
        return f"  {HEARD}  "

    monkeypatch.setattr("agent.voice.transcribe_file", fake)
    return fake, calls


def _events(body: str) -> list[dict]:
    return [json.loads(line[len("data:"):]) for line in body.splitlines() if line.startswith("data:")]


# --- hearing --------------------------------------------------------------

def test_what_was_said_comes_back_as_text_and_the_audio_is_gone(client, heard):
    _, calls = heard
    r = client.post("/api/voice/transcribe", files={"audio": ("turn.wav", b"RIFF-fake", "audio/wav")})

    assert r.status_code == 200, r.text
    assert r.json() == {"text": HEARD}
    assert calls[0]["existed"]
    assert calls[0]["language"] == "en"
    assert not calls[0]["path"].exists(), "the audio is not kept"
    assert list((Path(settings.DATA_DIR) / "tmp").iterdir()) == []


def test_the_audio_is_deleted_when_the_provider_fails(client, heard):
    fake, calls = heard
    fake.fail = True
    r = client.post("/api/voice/transcribe", files={"audio": ("turn.webm", b"fake", "audio/webm;codecs=opus")})

    assert r.status_code == 502
    assert not calls[0]["path"].exists()


def test_a_turn_too_long_or_of_an_unknown_kind_is_refused(client, heard):
    _, calls = heard
    big = b"0" * (voice.MAX_UTTERANCE_BYTES + 1)
    assert client.post("/api/voice/transcribe", files={"audio": ("t.wav", big, "audio/wav")}).status_code == 413
    assert client.post("/api/voice/transcribe", files={"audio": ("t.txt", b"x", "text/plain")}).status_code == 400
    assert calls == [], "nothing was sent"


# --- the turn -------------------------------------------------------------

def test_a_spoken_turn_is_an_ordinary_turn_with_one_instruction_more(client, mock_llm):
    opened = client.post("/api/conversations").json()["id"]

    events = _events(client.post(f"/api/conversations/{opened}/messages/stream",
                                 json={"text": HEARD, "voice": True}).text)

    assert events[-1]["done"] is True
    prompt = mock_llm.stream.call_args.kwargs["system_prompt"]
    assert "This turn is spoken aloud" in prompt
    stored = client.get(f"/api/conversations/{opened}/messages").json()
    assert [(m["role"], m["text"]) for m in stored] == [("user", HEARD), ("iris", "IRIS Mocked Response")]


def test_a_typed_turn_is_not_told_it_is_spoken(client, mock_llm):
    opened = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{opened}/messages/stream", json={"text": HEARD})
    assert "This turn is spoken aloud" not in mock_llm.stream.call_args.kwargs["system_prompt"]


# --- speaking -------------------------------------------------------------

class _Speech:
    """The provider's streaming speech response, replaced."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.closed = False

    def create(self, **kwargs):
        self.requests.append(kwargs)
        outer = self

        class Manager:
            def __enter__(self):
                class Response:
                    @staticmethod
                    def iter_bytes(chunk_size: int):
                        yield b"ID3-part-one"
                        yield b"-part-two"
                return Response()

            def __exit__(self, *exc):
                outer.closed = True

        return Manager()


@pytest.fixture
def speech(monkeypatch):
    fake = _Speech()

    class Client:
        class audio:
            class speech:
                with_streaming_response = fake

    class FakeIntelligence:
        openai_client = Client()

    monkeypatch.setattr("agent.voice.Intelligence", FakeIntelligence)
    return fake


def test_irises_words_come_back_as_streamed_speech(client, speech):
    r = client.post("/api/voice/speech", json={"text": "Beans would do well there."})

    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"ID3-part-one-part-two"
    assert speech.requests[0]["input"] == "Beans would do well there."
    assert speech.requests[0]["model"] == settings.TTS_MODEL
    assert speech.closed


def test_speech_refuses_nothing_and_too_much(client, speech):
    assert client.post("/api/voice/speech", json={"text": ""}).status_code == 422
    assert client.post("/api/voice/speech", json={"text": "x" * (voice.MAX_SPEECH_CHARS + 1)}).status_code == 422
    assert speech.requests == []


# --- cost first -----------------------------------------------------------

def test_the_estimate_says_what_a_turn_costs_and_sends_nothing(client, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the estimate must not call a model")
    monkeypatch.setattr("agent.voice.Intelligence.__init__", refuse)
    monkeypatch.setattr("agent.voice.transcribe_file", refuse)

    body = client.get("/api/voice/estimate").json()

    assert body["tokensIn"] > 0
    assert body["perTurn"].startswith("about $") or "price unknown" in body["perTurn"]


# --- only IRIS's own page -------------------------------------------------

@pytest.mark.parametrize(("path", "kwargs"), [
    ("/api/voice/transcribe", {"files": {"audio": ("t.wav", b"x", "audio/wav")}}),
    ("/api/voice/speech", {"json": {"text": "hello"}}),
])
def test_another_website_cannot_use_the_voice_routes(path, kwargs):
    async def exercise():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 3456))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            response = await client.post(path, headers={"Origin": "https://untrusted.example"}, **kwargs)
            assert response.status_code == 403
    asyncio.run(exercise())
