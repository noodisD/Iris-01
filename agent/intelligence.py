"""
Intelligence layer — the OpenAI chat client.

A pluggable multi-provider abstraction (llm_provider.py) and a Gemini fallback
both used to live here. Neither was ever reachable: nothing passed
use_gemini=True and chat_with_provider() was never called outside this module,
while the Gemini SDK it depended on reached end of support in November 2025.
"""

import logging
from typing import Any

from openai import AsyncOpenAI, OpenAI

from .config import settings

logger = logging.getLogger(__name__)


class Intelligence:
    """Thin wrapper over the OpenAI chat completions API."""

    def __init__(self, api_key: str | None = None, model: str = None):
        """Initialise the OpenAI client for this session."""
        self.openai_client = None
        self.model = model or settings.OPENAI_MODEL

        # Initialize OpenAI first (primary)
        openai_key = api_key or settings.OPENAI_API_KEY

        if openai_key and openai_key != "your_openai_api_key_here":
            try:
                self.openai_client = OpenAI(api_key=openai_key)
                self.async_client = AsyncOpenAI(api_key=openai_key)
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
        temperature: float = 0.7,
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

    def _chat_openai(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
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

            # Prepare request kwargs
            kwargs = {
                "model": self.model,
                "messages": full_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # Add tools if provided
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            # Call API
            response = self.openai_client.chat.completions.create(**kwargs)

            # Extract response
            if response.choices[0].message.content:
                return response.choices[0].message.content
            else:
                return "[No response content]"

        except Exception:
            # Deliberately propagated. Returning the message as a string made it
            # indistinguishable from a real reply: core.chat() persisted
            # "OpenAI API error: ..." into conversation_messages as Iris's own
            # words, and fed it back as context on later turns. The outer
            # handler in chat() could never see these, because this one caught
            # them first.
            logger.error("OpenAI chat call failed", exc_info=True)
            raise

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Asynchronous chat with optional tool calling

        Args:
            messages: List of {role, content} dicts
            system_prompt: System message defining behavior
            tools: Optional list of tool definitions for function calling
            temperature: Creativity level (0-1)
            max_tokens: Max response length

        Returns:
            Response text from the model
        """
        try:
            # Prepare messages with system prompt
            full_messages = [
                {"role": "system", "content": system_prompt},
                *messages
            ]

            # Prepare request kwargs
            kwargs = {
                "model": self.model,
                "messages": full_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # Add tools if provided
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            # Call API
            response = await self.async_client.chat.completions.create(**kwargs)

            # Extract response
            if response.choices[0].message.content:
                return response.choices[0].message.content
            else:
                return "[No response content]"

        except Exception as e:
            return f"Error calling API: {e!s}"

    def estimate_cost(self, messages: list[dict[str, str]]) -> dict[str, float]:
        """Rough estimate of API cost

        GPT-4o-mini: $0.15 per 1M input tokens, $0.60 per 1M output tokens
        Average: ~1.3 tokens per word

        Returns:
            Dict with estimated_input_cost and estimated_output_cost
        """
        # Count total words
        total_words = sum(len(msg.get("content", "").split()) for msg in messages)
        input_tokens = int(total_words * 1.3)
        output_tokens = 2000  # max_tokens assumption

        input_cost = (input_tokens / 1_000_000) * 0.15
        output_cost = (output_tokens / 1_000_000) * 0.60

        return {
            "estimated_input_cost": input_cost,
            "estimated_output_cost": output_cost,
            "total_estimated_cost": input_cost + output_cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
