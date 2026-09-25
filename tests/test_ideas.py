"""Idea reading stays out of the psychological engines.

These tests use a scripted chat double. Nothing here calls a live model.
"""

from __future__ import annotations

import json
from datetime import date


from agent.ideas.service import IdeaService
from agent.trackers.reflections import ReflectionService


PRICE = "A price is information. When a government fixes prices, it destroys the signal that tells people what is scarce."
QUOTE = "When a government fixes prices, it destroys the signal that tells people what is scarce."


class _Down:
    model = "scripted"

    def chat(self, messages, system_prompt, **kwargs):
        raise RuntimeError("provider down: " + PRICE)


class _Stance:
    model = "scripted"

    def chat(self, messages, system_prompt, **kwargs):
        if system_prompt.startswith("You are extracting"):
            return json.dumps({"ideas": [{
                "statement": "Price controls destroy the information prices carry about scarcity.",
                "domain": "economics",
                "quotes": [{"entryId": self.entry_id, "sourceType": "reflection", "text": QUOTE}],
            }]})
        if system_prompt.startswith("You are checking"):
            return json.dumps({"quotes": [{"i": 0, "stance": "not_stated"}]})
        raise AssertionError(system_prompt[:40])


def test_an_empty_archive_records_a_run_without_a_client(test_user, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("empty archive must not construct a model client")

    monkeypatch.setattr("agent.ideas.service.Intelligence", boom)
    result = IdeaService(test_user["id"]).discover()

    assert result["run"]["status"] == "complete"
    assert result["run"]["itemsRead"] == 0
    assert result["run"]["passesPlanned"] == 0
    assert result["run"]["error"] is None


def test_a_failed_model_call_stores_a_category_not_the_exception(test_user):
    ReflectionService(test_user["id"]).create_reflection(content=PRICE, reflection_date=date(2024, 1, 1))
    result = IdeaService(test_user["id"], intelligence=_Down()).discover()

    assert result["run"]["status"] == "failed"
    assert result["run"]["error"] == "model_failed"
    assert "provider down" not in json.dumps(result)
    assert PRICE not in json.dumps(result["run"])


def test_a_quote_that_does_not_show_a_position_is_not_stored(test_user):
    service = ReflectionService(test_user["id"])
    entry_id = service.create_reflection(content=PRICE, reflection_date=date(2024, 1, 1))
    model = _Stance()
    model.entry_id = entry_id

    result = IdeaService(test_user["id"], intelligence=model).discover()

    assert result["run"]["status"] == "complete"
    assert result["run"]["dropped"]["not_stated"] == 1
    assert result["run"]["proposed"] == 0
    assert IdeaService(test_user["id"]).review()["ideas"] == []


def test_an_invalid_domain_is_a_malformed_drop(test_user):
    service = ReflectionService(test_user["id"])
    entry_id = service.create_reflection(content=PRICE, reflection_date=date(2024, 1, 1))

    class Model:
        model = "scripted"

        def chat(self, messages, system_prompt, **kwargs):
            return json.dumps({"ideas": [{
                "statement": "Price controls destroy the information prices carry about scarcity.",
                "domain": "ideology",
                "quotes": [{"entryId": entry_id, "sourceType": "reflection", "text": QUOTE}],
            }]})

    result = IdeaService(test_user["id"], intelligence=Model()).discover()

    assert result["run"]["dropped"]["malformed"] == 1
    assert result["run"]["proposed"] == 0
    assert result["run"]["status"] == "complete"


def test_a_trading_pattern_is_stored_as_trading_not_economics(test_user):
    service = ReflectionService(test_user["id"])
    entry_id = service.create_reflection(content=PRICE, reflection_date=date(2024, 1, 1))

    class Model:
        model = "scripted"

        def chat(self, messages, system_prompt, **kwargs):
            if system_prompt.startswith("You are extracting"):
                return json.dumps({"ideas": [{
                    "statement": "A pattern is an edge only after it survives a forward test.",
                    "domain": "markets",
                    "quotes": [{"entryId": entry_id, "sourceType": "reflection", "text": QUOTE}],
                }]})
            if system_prompt.startswith("You are checking"):
                return json.dumps({"quotes": [{"i": 0, "stance": "endorsed"}]})
            return json.dumps({"ideaId": None})

    result = IdeaService(test_user["id"], intelligence=Model()).discover()
    review = IdeaService(test_user["id"]).review()

    assert result["run"]["status"] == "complete"
    assert result["run"]["proposed"] == 1
    assert review["ideas"][0]["idea"]["domain"] == "markets"


def test_a_source_edited_during_the_read_is_not_saved(test_user):
    reflections = ReflectionService(test_user["id"])
    entry_id = reflections.create_reflection(content=PRICE, reflection_date=date(2024, 1, 1))

    class Model:
        model = "scripted"

        def chat(self, messages, system_prompt, **kwargs):
            if system_prompt.startswith("You are extracting"):
                reflections.update_reflection(entry_id, content="The entry was rewritten while the model was reading it.")
                return json.dumps({"ideas": [{
                    "statement": "Price controls destroy the information prices carry about scarcity.",
                    "domain": "economics",
                    "quotes": [{"entryId": entry_id, "sourceType": "reflection", "text": QUOTE}],
                }]})
            if system_prompt.startswith("You are checking"):
                return json.dumps({"quotes": [{"i": 0, "stance": "endorsed"}]})
            return json.dumps({"ideaId": None})

    result = IdeaService(test_user["id"], intelligence=Model()).discover()

    assert result["run"]["dropped"]["source_changed"] == 1
    assert result["run"]["proposed"] == 0
    assert IdeaService(test_user["id"]).review()["ideas"] == []


def test_a_non_object_proposal_is_a_malformed_drop_not_a_failed_pass(test_user):
    service = ReflectionService(test_user["id"])
    entry_id = service.create_reflection(content=PRICE, reflection_date=date(2024, 1, 1))

    class Model:
        model = "scripted"

        def chat(self, messages, system_prompt, **kwargs):
            if system_prompt.startswith("You are extracting"):
                return json.dumps({"ideas": [
                    "Price controls are bad",
                    {
                        "statement": "Price controls destroy the information prices carry about scarcity.",
                        "domain": "economics",
                        "quotes": [{"entryId": entry_id, "sourceType": "reflection", "text": QUOTE}],
                    },
                ]})
            if system_prompt.startswith("You are checking"):
                return json.dumps({"quotes": [{"i": 0, "stance": "endorsed"}]})
            return json.dumps({"ideaId": None})

    result = IdeaService(test_user["id"], intelligence=Model()).discover()

    assert result["run"]["status"] == "complete"
    assert result["run"]["passesCompleted"] == 1
    assert result["run"]["dropped"]["malformed"] == 1
    assert result["run"]["proposed"] == 1
