"""Mis-hearings fixed against a second hearing, checked rather than trusted (ADR-0030).

Nothing is sent: the model's replies are scripted. Every line below is invented.
"""

from __future__ import annotations

import json

from agent import session_cleanup
from agent.session_voices import Heard

TURNS = [Heard("Ann", 0, 5, "I kept putting of the cold to my landlord"),
         Heard("Counsellor", 5, 9, "What happened when you finally called him"),
         Heard("Ann", 9, 12, "He agreed to fix the heating straight away")]
SECOND = [Heard("Ann", 0, 5, "I kept putting off the call to my landlord."),
          Heard("Counsellor", 5, 9, "What happened when you called him?")]


class Scripted:
    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def chat(self, messages, system_prompt, **kwargs):
        self.sent.append(messages[0]["content"])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply)


def test_a_mis_heard_word_is_fixed_and_logged_and_a_rewrite_is_refused():
    model = Scripted({"turns": [
        {"n": 0, "text": "I kept putting off the call to my landlord.",
         "changes": [{"from": "of the cold", "to": "off the call", "why": "second hearing"}]},
        {"n": 1, "text": "What happened?", "changes": []},
    ]})
    fixed, report = session_cleanup.tidy(TURNS, SECOND, "en", intelligence=model)
    assert "SECOND:" in model.sent[0] and "off the call" in model.sent[0]
    assert fixed[0].text == "I kept putting off the call to my landlord."
    assert fixed[1].text == TURNS[1].text, "a turn that lost half its words keeps Whisper's"
    assert fixed[2].text == TURNS[2].text, "a turn left out of the reply is unchanged"
    assert [(t.speaker, t.start) for t in fixed] == [(t.speaker, t.start) for t in TURNS]
    assert report["changes"] == [{"at": 0, "from": "of the cold", "to": "off the call", "why": "second hearing"}]
    assert report["refused"] == 1


def test_a_failed_request_leaves_the_words_and_unclear_spans_are_counted(monkeypatch):
    monkeypatch.setattr(session_cleanup, "CHUNK", 2)
    model = Scripted(RuntimeError("provider down"), {"turns": [
        {"n": 2, "text": "He agreed to fix the [unclear: heating straight] away", "changes": []}]})
    fixed, report = session_cleanup.tidy(TURNS, SECOND, "en", intelligence=model)
    assert [t.text for t in fixed[:2]] == [t.text for t in TURNS[:2]]
    assert report["unavailable"] == 2 and report["unclear"] == 1
