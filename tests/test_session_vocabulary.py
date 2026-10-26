"""The local list of session terms feeds Whisper and the search gloss, and nothing else.

The terms here are invented; the owner's list never leaves `data/`.
"""

import json
import subprocess

import pytest

from agent import local_whisper, session_vocabulary


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.config.settings.DATA_DIR", str(tmp_path))
    return tmp_path


def _install(data_dir, terms):
    (data_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (data_dir / "sessions" / "vocabulary.json").write_text(json.dumps({"terms": terms}), encoding="utf-8")


def test_without_the_list_nothing_changes(data_dir):
    assert session_vocabulary.terms() == []
    assert session_vocabulary.hotwords("pl") is None
    assert session_vocabulary.gloss_line() == ""


def test_an_unreadable_list_is_ignored(data_dir):
    (data_dir / "sessions").mkdir()
    (data_dir / "sessions" / "vocabulary.json").write_text("{not json", encoding="utf-8")
    assert session_vocabulary.terms() == []


def test_the_gloss_renders_each_term_as_given(data_dir):
    _install(data_dir, [{"pl": "kłębek", "en": "tangle (a knot of worries)"}, {"pl": "przystań", "en": "harbour"},
                        {"pl": " ", "en": "skipped"}])
    assert session_vocabulary.gloss_line() == (
        "Render these recurring terms as given: kłębek → tangle (a knot of worries); przystań → harbour.")


def test_whisper_listens_for_the_terms_only_in_a_recording_that_may_be_polish(data_dir):
    _install(data_dir, [{"pl": "kłębek", "en": "tangle"}, {"pl": "przystań", "en": "harbour"}])
    assert session_vocabulary.hotwords("pl") == "kłębek przystań"
    assert session_vocabulary.hotwords(None) == "kłębek przystań"
    assert session_vocabulary.hotwords("en") is None


def test_the_whisper_worker_is_given_the_terms(data_dir, tmp_path, monkeypatch):
    _install(data_dir, [{"pl": "kłębek", "en": "tangle"}])
    python = tmp_path / "bin" / "python"
    python.parent.mkdir()
    python.touch()
    monkeypatch.setattr("agent.config.settings.WHISPER_PYTHON", str(python))
    seen = []

    def run(command, **_):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"device": "cpu", "words": []}), stderr="")
    monkeypatch.setattr(local_whisper.subprocess, "run", run)
    local_whisper.words(tmp_path / "a.m4a", "pl")
    local_whisper.words(tmp_path / "a.m4a", "en")
    assert seen[0][-2:] == ["--hotwords", "kłębek"]
    assert "--hotwords" not in seen[1]
