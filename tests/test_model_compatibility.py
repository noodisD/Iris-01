"""The OpenAI call shape has to work on the models that actually exist.

IRIS sent `max_tokens` and a custom `temperature`. Both are rejected by the
GPT-5 family and the o-series, so changing OPENAI_MODEL — which reads like a
configuration change — would have made every chat call 400. And a reasoning
model draws its thinking from the same completion budget, so a cap sized for
the visible answer can leave nothing for it: the call succeeds and returns "".

These tests mock at the SDK boundary, never at the seam being verified.
"""

import pytest
from openai import BadRequestError

from agent.intelligence import Intelligence, _REJECTS_TEMPERATURE


class _Message:
    def __init__(self, content): self.content = content


class _Choice:
    def __init__(self, content, finish_reason="stop"):
        self.message, self.finish_reason = _Message(content), finish_reason


class _Usage:
    completion_tokens_details = None


class _Response:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_Choice(content, finish_reason)]
        self.usage = _Usage()


def _bad_request(message):
    """A BadRequestError shaped like the real one, without a live call."""
    import httpx

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(400, request=request, json={"error": {"message": message}})
    return BadRequestError(message, response=response, body={"error": {"message": message}})


@pytest.fixture
def iris(monkeypatch):
    monkeypatch.setattr("agent.config.settings.OPENAI_API_KEY", "sk-test-not-used")
    return Intelligence(api_key="sk-test-not-used", model="test-model")


def test_the_modern_token_parameter_is_used(iris, monkeypatch):
    """max_completion_tokens is accepted by every current model; max_tokens is
    rejected by the newer ones. There is one spelling, so no branch to get
    wrong."""
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return _Response("hello")

    monkeypatch.setattr(iris.openai_client.chat.completions, "create", fake)
    iris.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s", max_tokens=1234)

    assert seen["max_completion_tokens"] == 1234
    assert "max_tokens" not in seen, "the deprecated spelling must not be sent"


def test_a_model_that_refuses_a_custom_temperature_still_works(iris, monkeypatch):
    """Reasoning models accept only their default temperature. IRIS asks for
    0.7; being refused must not be an outage."""
    _REJECTS_TEMPERATURE.discard("test-model")
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        if "temperature" in kwargs:
            raise _bad_request("Unsupported value: 'temperature' does not support 0.7")
        return _Response("hello")

    monkeypatch.setattr(iris.openai_client.chat.completions, "create", fake)
    assert iris.chat(messages=[{"role": "user", "content": "hi"}],
                     system_prompt="s", temperature=0.7) == "hello"

    assert len(calls) == 2, "one rejected attempt, then one without temperature"
    assert "temperature" in calls[0] and "temperature" not in calls[1]


def test_the_refusal_is_learned_once_not_paid_per_call(iris, monkeypatch):
    _REJECTS_TEMPERATURE.discard("test-model")
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        if "temperature" in kwargs:
            raise _bad_request("Unsupported value: 'temperature' does not support 0.7")
        return _Response("hello")

    monkeypatch.setattr(iris.openai_client.chat.completions, "create", fake)
    iris.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s", temperature=0.7)
    iris.chat(messages=[{"role": "user", "content": "again"}], system_prompt="s", temperature=0.7)

    assert len(calls) == 3, "the second call must not repeat the rejected attempt"
    _REJECTS_TEMPERATURE.discard("test-model")


def test_an_unrelated_bad_request_is_not_swallowed(iris, monkeypatch):
    """The retry is narrow. Any other 400 must surface."""
    def fake(**kwargs):
        raise _bad_request("Invalid value for 'messages': too long")

    monkeypatch.setattr(iris.openai_client.chat.completions, "create", fake)
    with pytest.raises(BadRequestError):
        iris.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s")


def test_an_empty_reply_raises_instead_of_becoming_iris_speaking(iris, monkeypatch):
    """A reasoning model that spends its whole budget thinking returns "" with
    finish_reason='length' and a 200. This used to return the literal string
    "[No response content]", which is long enough to pass the theme-summary
    length guard and become a theme's name."""
    monkeypatch.setattr(iris.openai_client.chat.completions, "create",
                        lambda **k: _Response("", finish_reason="length"))

    with pytest.raises(RuntimeError, match="returned no content"):
        iris.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s", max_tokens=20)


def test_the_message_says_how_to_fix_a_starved_budget(iris, monkeypatch):
    monkeypatch.setattr(iris.openai_client.chat.completions, "create",
                        lambda **k: _Response("", finish_reason="length"))
    with pytest.raises(RuntimeError) as e:
        iris.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s", max_tokens=20)
    assert "max_completion_tokens=20" in str(e.value)
    assert "raise it" in str(e.value)


def test_token_budgets_leave_room_for_reasoning():
    """Every call site's cap must be large enough that a reasoning model has
    room to answer after thinking. 20 tokens produced an empty summary."""
    import inspect
    from agent import core, persistence
    from agent.constants import DEFAULT_MAX_TOKENS

    assert DEFAULT_MAX_TOKENS >= 1000
    for module in (core, persistence):
        for line in inspect.getsource(module).splitlines():
            stripped = line.strip()
            if stripped.startswith("max_tokens=") and stripped.rstrip(",").split("=")[1].isdigit():
                budget = int(stripped.rstrip(",").split("=")[1])
                assert budget >= 300, (
                    f"{module.__name__} caps a call at {budget} tokens; a reasoning "
                    "model can spend that before producing any output"
                )
