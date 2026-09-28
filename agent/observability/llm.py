"""One span per outbound model call, including calls that stream."""

from __future__ import annotations

import time
from collections.abc import Mapping
from types import TracebackType
from typing import Literal, Self

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from agent.observability.content import MAX_TEXT, render_text
from agent.observability.hub import hub
from agent.observability.tracing import current_budget, mark_error, recording, start_detached

Operation = Literal["chat", "chat_stream", "embeddings", "transcription", "speech"]


def _purpose(explicit: str | None) -> str:
    if explicit:
        return explicit
    current = trace.get_current_span()
    component = ""
    attributes = getattr(current, "attributes", None) or {}
    if isinstance(attributes, Mapping):
        component = str(attributes.get("iris.component") or "")
    if component == "http":
        return "request"
    name = getattr(current, "name", None)
    return str(name) if name else "request"


def _int_attr(value: object, name: str) -> int | None:
    found = getattr(value, name, None)
    if type(found) is int:
        return found
    return None


class LlmCall:
    def __init__(
        self,
        operation: Operation,
        model: str,
        *,
        prompt: str | None = None,
        purpose: str | None = None,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        self.operation = operation
        self.model = model
        self._finished = False
        self._started = time.perf_counter()
        self._ttft = False
        self._output_bytes = 0
        from agent.config import settings

        base = settings.OPENAI_BASE_URL or "api.openai.com"
        attrs: dict[str, object] = {
            "gen_ai.system": "openai",
            "gen_ai.operation.name": "chat" if operation == "chat_stream" else operation,
            "gen_ai.request.model": model,
            "iris.llm.base_url": base,
            "iris.llm.purpose": _purpose(purpose),
        }
        if prompt is not None:
            attrs["iris.llm.prompt"] = render_text(prompt, MAX_TEXT)
        if attributes:
            attrs.update(attributes)
        try:
            self.span = start_detached(f"llm.{operation}", "llm", attrs, kind=SpanKind.CLIENT)
        except Exception:
            hub.note_internal()
            self.span = trace.INVALID_SPAN

    def first_output(self) -> None:
        if self._ttft or not self.span.is_recording():
            self._ttft = True
            return
        self._ttft = True
        try:
            self.span.set_attribute("iris.llm.ttft_ms", (time.perf_counter() - self._started) * 1000)
        except Exception:
            hub.note_internal()

    def usage(self, usage: object) -> None:
        if usage is None or not self.span.is_recording():
            return
        try:
            prompt = _int_attr(usage, "prompt_tokens")
            completion = _int_attr(usage, "completion_tokens")
            details = getattr(usage, "completion_tokens_details", None)
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            reasoning = _int_attr(details, "reasoning_tokens") if details is not None else None
            cached = _int_attr(prompt_details, "cached_tokens") if prompt_details is not None else None
            tokens = 0
            if prompt is not None:
                self.span.set_attribute("gen_ai.usage.input_tokens", prompt)
                tokens += prompt
            if completion is not None:
                self.span.set_attribute("gen_ai.usage.output_tokens", completion)
                tokens += completion
            if reasoning is not None:
                self.span.set_attribute("iris.llm.reasoning_tokens", reasoning)
            if cached is not None:
                self.span.set_attribute("iris.llm.cached_tokens", cached)
            budget = current_budget()
            if budget is not None:
                budget.llm_tokens += tokens
            from agent.observability import metrics

            metrics.record_tokens(self.model, prompt or 0, completion or 0)
        except Exception:
            hub.note_internal()

    def output(self, text: object) -> None:
        if not isinstance(text, str) or not self.span.is_recording():
            return
        try:
            self.span.set_attribute("iris.llm.output", render_text(text, MAX_TEXT))
        except Exception:
            hub.note_internal()

    def add_output_bytes(self, count: int) -> None:
        self._output_bytes += count
        if self.span.is_recording():
            try:
                self.span.set_attribute("iris.llm.output_bytes", self._output_bytes)
            except Exception:
                hub.note_internal()

    def finish(self, error: BaseException | None = None, *, cancelled: bool = False) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            if self.span.is_recording():
                if cancelled:
                    self.span.set_attribute("iris.llm.cancelled", True)
                self._cost()
                if error is not None:
                    mark_error(self.span, error)
            self.span.end()
            budget = current_budget()
            if budget is not None and recording():
                budget.llm_calls += 1
        except Exception:
            hub.note_internal()

    def _cost(self) -> None:
        try:
            from agent.intelligence import Intelligence
        except Exception:
            return
        price = getattr(Intelligence, "PRICE_PER_MTOK", {}).get(self.model)
        if not price:
            return
        attributes = getattr(self.span, "attributes", None) or {}
        prompt = attributes.get("gen_ai.usage.input_tokens")
        completion = attributes.get("gen_ai.usage.output_tokens")
        if not isinstance(prompt, int) or not isinstance(completion, int):
            return
        in_price, out_price = price
        cost = (prompt * in_price + completion * out_price) / 1_000_000
        self.span.set_attribute("iris.llm.cost_usd", cost)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.finish(exc)
