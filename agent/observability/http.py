"""Pure ASGI tracing for every door except the Observatory's own reads."""

from __future__ import annotations

import time
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.datastructures import MutableHeaders
from starlette.routing import Match

from agent.observability.content import MAX_BODY, MAX_STATUS, render_text
from agent.observability.hub import hub
from agent.observability.tracing import (
    close_budget,
    open_budget,
    recording,
    suppressed,
)

_TEXTUAL = ("application/json", "text/", "application/x-www-form-urlencoded")
_RESPONSE_TEXT = ("application/json", "text/", "text/event-stream")


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    carrier: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        carrier[key.decode("latin1").lower()] = value.decode("latin1")
    return carrier


def _header(headers: dict[str, str], name: str) -> str:
    return headers.get(name.lower(), "")


def _textual(content_type: str, prefixes: tuple[str, ...]) -> bool:
    base = content_type.split(";", 1)[0].strip().lower()
    return any(base.startswith(prefix) for prefix in prefixes)


def _decode(chunks: list[bytes], total: int) -> str:
    raw = b"".join(chunks)
    if len(raw) > total:
        raw = raw[:total]
    return raw.decode("utf-8", errors="replace")


def _take(chunks: list[bytes], kept: int, body: bytes) -> tuple[int, bool]:
    """Keep only the remaining byte budget. A huge final chunk cannot slip through."""
    room = MAX_BODY - kept
    if room <= 0:
        return kept, bool(body)
    if len(body) <= room:
        if body:
            chunks.append(body)
        return kept + len(body), False
    chunks.append(body[:room])
    return MAX_BODY, True


def _expose_request(
    current: Any,
    chunks: list[bytes],
    content_type: str,
    capture: bool,
    truncated: bool,
) -> None:
    """Set request input once the application has consumed the final chunk."""
    try:
        current.set_attribute("iris.http.request_content_type", content_type)
        current.set_attribute("iris.http.request_body_complete", True)
        current.set_attribute("iris.http.request_body_truncated", truncated)
        if capture:
            current.set_attribute(
                "iris.http.request_body",
                render_text(_decode(chunks, MAX_BODY), MAX_BODY),
            )
    except Exception:
        hub.note_internal()


def route_template(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    app = scope.get("app")
    router = getattr(app, "router", None)
    for candidate in getattr(router, "routes", []) or []:
        matches = getattr(candidate, "matches", None)
        if matches is None:
            continue
        try:
            match, _child = candidate.matches(scope)
        except Exception:
            hub.note_internal()
            continue
        if match == Match.FULL:
            found = getattr(candidate, "path", None)
            if isinstance(found, str) and found:
                return found
    return "<unmatched>"


class TracingMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not recording():
            await self.app(scope, receive, send)
            return
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path.startswith(("/api/observatory/", "/assets/")):
            with suppressed():
                await self.app(scope, receive, send)
            return
        try:
            await self._traced(scope, receive, send, path)
        except Exception:
            raise

    async def _traced(self, scope: dict[str, Any], receive: Any, send: Any, path: str) -> None:
        headers = _headers(scope)
        method = scope.get("method") or "GET"
        door = (
            "lan"
            if scope.get("iris_lan")
            else "tailnet"
            if scope.get("iris_tailnet")
            else "loopback"
        )
        client = scope.get("client")
        address = client[0] if client else ""
        parent = extract(headers)
        route = route_template(scope)
        resolved = bool(route) and route != "<unmatched>"
        tracer = trace.get_tracer("iris")
        attributes: dict[str, str] = {
            "iris.component": "http",
            "http.request.method": method,
            "url.path": path,
            "url.query": scope.get("query_string", b"").decode("latin1"),
            "iris.door": door,
            "iris.client": _header(headers, "x-iris-client") or "unknown",
            "client.address": address,
            "user_agent.original": _header(headers, "user-agent"),
            "iris.http.request_content_type": _header(headers, "content-type"),
        }
        if resolved:
            attributes["http.route"] = route
        current = tracer.start_span(
            f"{method} {route if resolved else path}",
            context=parent,
            kind=SpanKind.SERVER,
            attributes=attributes,
        )
        token = otel_context.attach(trace.set_span_in_context(current))
        budget_token = open_budget(current)
        request_type = _header(headers, "content-type")
        capture_request = _textual(request_type, _TEXTUAL)
        request_chunks: list[bytes] = []
        request_bytes = 0
        request_kept = 0
        request_truncated = False
        request_complete = False
        response_chunks: list[bytes] = []
        response_bytes = 0
        response_kept = 0
        response_truncated = False
        response_type = ""
        capture_response = False
        status_code = 500
        started = time.perf_counter()
        error: BaseException | None = None

        async def receive_wrapped() -> Any:
            nonlocal request_bytes, request_kept, request_truncated, request_complete
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body") or b""
                request_bytes += len(body)
                if capture_request:
                    request_kept, overflow = _take(request_chunks, request_kept, body)
                    request_truncated = request_truncated or overflow
                if not message.get("more_body"):
                    request_complete = True
                    _expose_request(
                        current,
                        request_chunks,
                        request_type,
                        capture_request,
                        request_truncated or request_bytes > MAX_BODY,
                    )
            return message

        async def send_wrapped(message: dict[str, Any]) -> None:
            nonlocal status_code, response_bytes, response_kept, response_truncated
            nonlocal capture_response, response_type
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 500)
                current.set_attribute("iris.http.ttfb_ms", (time.perf_counter() - started) * 1000)
                mutable = MutableHeaders(scope=message)
                mutable.append("x-iris-trace", f"{current.get_span_context().trace_id:032x}")
                response_type = mutable.get("content-type", "")
                streaming = response_type.startswith(("text/event-stream", "audio/mpeg"))
                current.set_attribute("iris.http.streaming", streaming)
                current.set_attribute("iris.http.response_content_type", response_type)
                capture_response = _textual(response_type, _RESPONSE_TEXT)
            elif message.get("type") == "http.response.body":
                body = message.get("body") or b""
                response_bytes += len(body)
                if capture_response:
                    response_kept, overflow = _take(response_chunks, response_kept, body)
                    response_truncated = response_truncated or overflow
            await send(message)

        try:
            await self.app(scope, receive_wrapped, send_wrapped)
        except BaseException as exc:
            error = exc
            raise
        finally:
            try:
                self._finish(
                    current,
                    scope,
                    method,
                    door,
                    started,
                    status_code,
                    error,
                    request_chunks,
                    request_bytes,
                    request_complete,
                    request_truncated,
                    request_type,
                    capture_request,
                    response_chunks,
                    response_bytes,
                    response_truncated,
                    response_type,
                    capture_response,
                )
            except Exception:
                hub.note_internal()
            finally:
                try:
                    close_budget(budget_token, current)
                except Exception:
                    hub.note_internal()
                try:
                    current.end()
                except Exception:
                    hub.note_internal()
                otel_context.detach(token)

    def _finish(
        self,
        current: Any,
        scope: dict[str, Any],
        method: str,
        door: str,
        started: float,
        status_code: int,
        error: BaseException | None,
        request_chunks: list[bytes],
        request_bytes: int,
        request_complete: bool,
        request_truncated: bool,
        request_type: str,
        capture_request: bool,
        response_chunks: list[bytes],
        response_bytes: int,
        response_truncated: bool,
        response_type: str,
        capture_response: bool,
    ) -> None:
        route = route_template(scope)
        current.update_name(f"{method} {route}")
        current.set_attribute("http.route", route)
        current.set_attribute("http.response.status_code", status_code)
        current.set_attribute("http.request.body.size", request_bytes)
        current.set_attribute("http.response.body.size", response_bytes)
        current.set_attribute("iris.http.request_content_type", request_type)
        current.set_attribute("iris.http.response_content_type", response_type)
        current.set_attribute("iris.http.request_body_complete", request_complete)
        current.set_attribute("iris.http.response_body_complete", error is None)
        current.set_attribute(
            "iris.http.request_body_truncated",
            request_truncated or request_bytes > MAX_BODY,
        )
        current.set_attribute(
            "iris.http.response_body_truncated",
            response_truncated or response_bytes > MAX_BODY,
        )
        if request_complete and capture_request:
            current.set_attribute(
                "iris.http.request_body",
                render_text(_decode(request_chunks, MAX_BODY), MAX_BODY),
            )
        if capture_response and response_chunks:
            current.set_attribute(
                "iris.http.response_body",
                render_text(_decode(response_chunks, MAX_BODY), MAX_BODY),
            )
        if error is not None:
            current.record_exception(error)
            current.set_status(
                Status(StatusCode.ERROR, f"{type(error).__name__}: {error}"[:MAX_STATUS])
            )
        elif status_code >= 500:
            current.set_status(Status(StatusCode.ERROR, f"HTTP {status_code}"))
        from agent.observability import metrics

        metrics.record_http(
            (time.perf_counter() - started),
            method,
            route,
            status_code,
            door,
        )
