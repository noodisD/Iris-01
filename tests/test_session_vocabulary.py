"""The local list of session terms feeds the search gloss, and nothing else.

The terms here are invented; the owner's list never leaves `data/`.
"""

import json

import pytest

from agent import session_vocabulary


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.config.settings.DATA_DIR", str(tmp_path))
    return tmp_path


def _install(data_dir, terms):
    (data_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (data_dir / "sessions" / "vocabulary.json").write_text(json.dumps({"terms": terms}), encoding="utf-8")


def test_without_the_list_nothing_changes(data_dir):
    assert session_vocabulary.terms() == []
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
