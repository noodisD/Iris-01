"""
Intelligence layer — the OpenAI chat client.

A pluggable multi-provider abstraction (llm_provider.py) and a Gemini fallback
both used to live here. Neither was ever reachable: nothing passed
use_gemini=True and chat_with_provider() was never called outside this module,
while the Gemini SDK it depended on reached end of support in November 2025.
"""

import logging
from collections.abc import Iterator
from typing import Any

from openai import BadRequestError, OpenAI

from .config import settings

logger = logging.getLogger(__name__)

#: Models that rejected a non-default `temperature`. Learned from the API's own
#: error rather than hardcoded against model names: new models keep appearing
#: and a hardcoded list is wrong the moment one does. GPT-5 and the o-series
#: accept only the default, so IRIS runs at whatever the model's default is and
#: says so, rather than sending a value that is silently ignored.
_REJECTS_TEMPERATURE: set[str] = set()


class Intelligence:
    """Thin wrapper over the OpenAI chat completions API."""

    #: Dollars per million tokens, input and output, from OpenAI's pricing page
    #: as read on 21 September 2026. Here so a run can say what it is about to
    #: spend before it spends it; wrong the moment prices move, which is why
    #: anything not listed is reported as tokens alone rather than guessed at.
    PRICE_PER_MTOK = {
        "gpt-5.6-luna": (0.20, 1.20),
        "gpt-5.6-terra": (2.00, 12.00),
        "gpt-5.6-sol": (5.00, 30.00),
    }

    @classmethod
    def estimate(cls, model: str, tokens_in: int, tokens_out: int = 0) -> str:
        """What a run of this size would cost, said in words rather than hidden."""
        price = cls.PRICE_PER_MTOK.get(model)
        if price is None:
            return f"{tokens_in // 1000}k tokens in on {model} (price unknown here)"
        dollars = tokens_in / 1_000_000 * price[0] + tokens_out / 1_000_000 * price[1]
        return f"{tokens_in // 1000}k tokens in on {model}, about ${dollars:.2f}"

    def __init__(self, api_key: str | None = None, model: str = None):
        """Initialise the OpenAI client for this session."""
        self.openai_client = None
        self.model = model or settings.OPENAI_MODEL

        # Initialize OpenAI first (primary)
        openai_key = api_key or settings.OPENAI_API_KEY

        if openai_key and openai_key != "your_openai_api_key_here":
            try:
                self.openai_client = OpenAI(api_key=openai_key)
            except Exception as e:
                print(f"⚠️  OpenAI initialization failed: {e}")

        if not self.openai_client:
            raise ValueError("No API key configured. Set OPENAI_API_KEY in .env")

    def set_model(self, model: str) -> None:
        """Switch the active model."""
        self.model = model

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = 0.7,
        max_tokens: int = 1000,
        model: str | None = None,
    ) -> str:
        """Send a conversation to OpenAI and return the reply text.

        Args:
            messages: List of {role, content} dicts
            system_prompt: System message defining behavior
            tools: Optional tool definitions for function calling
            temperature: Creativity level (0-1)
            max_tokens: Max response length
            model: Optional model override

        Returns:
            Response text from the model
        """
        try:
            if self.openai_client:
                return self._chat_openai(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools
                )
            else:
                raise RuntimeError("No LLM client is configured")

        except Exception as e:
            # Deliberately raised, not returned. Returning the message meant
            # core.chat() persisted "Error calling API: ..." into
            # conversation_messages as Iris's own reply — permanent history the
            # user never said anything to provoke, and which was then re-fed as
            # context on later turns.
            logger.error(f"LLM call failed: {e}")
            raise

    def stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float | None = 0.7,
        max_tokens: int = 1000,
    ) -> Iterator[str]:
        """The reply as it is generated, piece by piece.

        Chat used to wait for the whole reply and then drip it to the screen a
        word at a time, so the owner waited twice: once for the model, again for
        the animation. This yields each fragment as the model produces it.

        The same guards as `chat`: a model that rejects a custom temperature is
        remembered and retried without one (the rejection arrives when the
        request is made, before anything is yielded), and a reply that ends
        with no content is an error rather than an empty message.
        """
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "max_completion_tokens": max_tokens,
            "stream": True,
        }
        if temperature is not None and self.model not in _REJECTS_TEMPERATURE:
            kwargs["temperature"] = temperature
        try:
            chunks = self.openai_client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            if "temperature" not in str(e) or "temperature" not in kwargs:
                raise
            _REJECTS_TEMPERATURE.add(self.model)
            del kwargs["temperature"]
            chunks = self.openai_client.chat.completions.create(**kwargs)

        produced = False
        finish_reason = None
        for chunk in chunks:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason or finish_reason
            delta = getattr(choice.delta, "content", None)
            if delta:
                produced = True
                yield delta
        if not produced:
            raise RuntimeError(
                f"{self.model} returned no content (finish_reason={finish_reason}, "
                f"max_completion_tokens={max_tokens}).")

    def _chat_openai(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float | None = 0.7,
        max_tokens: int = 1000,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Call OpenAI API (fallback)

        Args:
            messages: Conversation messages
            system_prompt: System context
            temperature: Sampling temperature
            max_tokens: Response length limit
            tools: Optional function calling tools

        Returns:
            Response text
        """
        try:
            # Prepare messages with system prompt
            full_messages = [
                {"role": "system", "content": system_prompt},
                *messages
            ]

            # max_completion_tokens, not max_tokens: the GPT-5 family and the
            # o-series reject the older spelling outright, and every model still
            # supported accepts this one, so there is no branch to get wrong.
            kwargs = {
                "model": self.model,
                "messages": full_messages,
                "max_completion_tokens": max_tokens,
            }
            if temperature is not None and self.model not in _REJECTS_TEMPERATURE:
                kwargs["temperature"] = temperature

            # Add tools if provided
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            try:
                response = self.openai_client.chat.completions.create(**kwargs)
            except BadRequestError as e:
                if "temperature" not in str(e) or "temperature" not in kwargs:
                    raise
                # Reasoning models accept only the default temperature. Remember
                # it for this model so the round trip is paid once, not per call.
                logger.info(
                    f"{self.model} does not accept a custom temperature; "
                    "using the model default from here on"
                )
                _REJECTS_TEMPERATURE.add(self.model)
                del kwargs["temperature"]
                response = self.openai_client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            if choice.message.content:
                return choice.message.content

            # An empty reply is a failure, not a reply. On a reasoning model the
            # usual cause is a budget too small to leave room for output after
            # the thinking, which is silent: the call succeeds and returns "".
            # This used to return the string "[No response content]", which is
            # long enough to pass the theme-summary length guard and become a
            # theme's name.
            reasoning = getattr(
                getattr(response.usage, "completion_tokens_details", None),
                "reasoning_tokens", None,
            )
            raise RuntimeError(
                f"{self.model} returned no content "
                f"(finish_reason={choice.finish_reason}"
                + (f", reasoning_tokens={reasoning}" if reasoning else "")
                + f", max_completion_tokens={max_tokens}). "
                "If finish_reason is 'length', the budget was spent before any "
                "output was produced — raise it."
            )

        except Exception:
            # Deliberately propagated. Returning the message as a string made it
            # indistinguishable from a real reply: core.chat() persisted
            # "OpenAI API error: ..." into conversation_messages as Iris's own
            # words, and fed it back as context on later turns. The outer
            # handler in chat() could never see these, because this one caught
            # them first.
            logger.error("OpenAI chat call failed", exc_info=True)
            raise
