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

from agent.intelligence import Intelligence, _LearnedModels, _REJECTS_TEMPERATURE


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


def test_the_refusal_is_remembered_across_a_restart(iris, monkeypatch):
    """Forgetting on restart meant one refused request after every restart."""
    _REJECTS_TEMPERATURE.discard("test-model")

    def fake(**kwargs):
        if "temperature" in kwargs:
            raise _bad_request("Unsupported value: 'temperature' does not support 0.7")
        return _Response("hello")

    monkeypatch.setattr(iris.openai_client.chat.completions, "create", fake)
    iris.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s", temperature=0.7)

    after_restart = _LearnedModels("rejects_temperature")
    assert "test-model" in after_restart
    _REJECTS_TEMPERATURE.discard("test-model")
    assert "test-model" not in _LearnedModels("rejects_temperature")


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


def _capacity_unavailable():
    """The 429 Flex returns when OpenAI has no spare capacity; it is not charged."""
    import httpx
    from openai import RateLimitError

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request, json={"error": {"message": "Resource Unavailable"}})
    return RateLimitError("Resource Unavailable", response=response,
                          body={"error": {"message": "Resource Unavailable"}})


@pytest.fixture
def flex(monkeypatch):
    monkeypatch.setattr("agent.config.settings.OPENAI_API_KEY", "sk-test-not-used")
    model = Intelligence(api_key="sk-test-not-used", model="test-model", service_tier="flex")
    # with_options returns a copy of the client; keep the one the test patches.
    monkeypatch.setattr(model.openai_client, "with_options", lambda **_: model.openai_client)
    return model


def test_background_work_asks_for_flex(flex, monkeypatch):
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return _Response("hello")

    monkeypatch.setattr(flex.openai_client.chat.completions, "create", fake)
    assert flex.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s") == "hello"
    assert seen["service_tier"] == "flex"


def test_flex_waits_out_unavailable_capacity_and_sends_again(flex, monkeypatch):
    calls, pauses = [], []

    def fake(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise _capacity_unavailable()
        return _Response("hello")

    monkeypatch.setattr(flex.openai_client.chat.completions, "create", fake)
    monkeypatch.setattr("agent.intelligence.time.sleep", pauses.append)
    assert flex.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s") == "hello"
    assert len(calls) == 3
    assert pauses == [15, 60]


def test_flex_gives_up_after_the_last_pause_so_the_queue_retries_later(flex, monkeypatch):
    from openai import RateLimitError

    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        raise _capacity_unavailable()

    monkeypatch.setattr(flex.openai_client.chat.completions, "create", fake)
    monkeypatch.setattr("agent.intelligence.time.sleep", lambda _: None)
    with pytest.raises(RateLimitError):
        flex.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s")
    assert len(calls) == 4


def test_a_standard_request_is_not_held_back(iris, monkeypatch):
    from openai import RateLimitError

    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        raise _capacity_unavailable()

    monkeypatch.setattr(iris.openai_client.chat.completions, "create", fake)
    monkeypatch.setattr("agent.intelligence.time.sleep", lambda _: pytest.fail("standard requests do not pause"))
    with pytest.raises(RateLimitError):
        iris.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s")
    assert len(calls) == 1
    assert "service_tier" not in calls[0]


def test_an_estimate_on_flex_is_half_the_standard_price():
    assert Intelligence.estimate("gpt-6-luna", 2_000_000, 1_000_000) == \
        "2000k tokens in on gpt-6-luna, about $0.70"
    assert Intelligence.estimate("gpt-6-luna", 2_000_000, 1_000_000, service_tier="flex") == \
        "2000k tokens in on gpt-6-luna on Flex, about $0.35"


def test_a_background_request_that_never_returns_fails_at_its_deadline(flex, monkeypatch):
    """One Flex request once held the patterns run for ten hours with no error."""
    import threading

    release = threading.Event()

    def never(**kwargs):
        release.wait(5)
        return _Response("too late")

    monkeypatch.setattr(flex.openai_client.chat.completions, "create", never)
    monkeypatch.setattr("agent.intelligence.FLEX_DEADLINE_SECONDS", 0.2)
    try:
        with pytest.raises(TimeoutError, match="deadline"):
            flex.chat(messages=[{"role": "user", "content": "hi"}], system_prompt="s")
    finally:
        release.set()
