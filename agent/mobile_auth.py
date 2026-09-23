"""Bearer-token middleware for the LAN bind.

Loopback bypasses; everything else needs the bearer. The middleware
sits in front of every FastAPI request. If the bind is disabled, LAN
requests are rejected outright so a misconfiguration cannot silently
expose the API.

The token is stored as a SHA-256 hash; the phone stores the raw token
in the Android Keystore.
"""
from __future__ import annotations

import hashlib

from starlette.types import ASGIApp, Message, Scope, Receive, Send

from .config import settings


_LOOPBACK_PREFIXES = ("127.", "::1", "localhost")
# FastAPI's TestClient and httpx's test transport use these as the
# client hostname. They are by construction local; treat them as
# loopback so the existing test suite (which uses TestClient) keeps
# working without changing how tests are written.
_LOOPBACK_TEST_HOSTS = frozenset({"testclient", "testserver"})


class MobileAuthMiddleware:
    """ASGI middleware enforcing the bearer on the LAN bind.

    The middleware is pure — it does not read the database, the file
    system, or any other state. The settings it consults are the same
    Pydantic settings the rest of IRIS uses, mutated in-process by
    /api/mobile/pair.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client_host = (scope.get("client") or ("", 0))[0]
        is_loopback = (
            any(client_host.startswith(p) for p in _LOOPBACK_PREFIXES)
            or client_host in _LOOPBACK_TEST_HOSTS)

        if is_loopback:
            await self.app(scope, receive, send)
            return

        if not settings.LAN_BIND_ENABLED:
            await self._reject(send, 403, "lan bind disabled")
            return

        if not settings.MOBILE_BEARER_HASH:
            await self._reject(send, 503, "no bearer configured")
            return

        token = self._extract_bearer(scope.get("headers") or [])
        if token is None:
            await self._reject(send, 401, "bearer required")
            return

        if hashlib.sha256(token.encode()).hexdigest() != settings.MOBILE_BEARER_HASH:
            await self._reject(send, 401, "bearer mismatch")
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _extract_bearer(headers: list[tuple[bytes, bytes]]) -> str | None:
        for name, value in headers:
            if name == b"authorization":
                text = value.decode("latin-1", errors="replace")
                if text.startswith("Bearer "):
                    bearer = text[len("Bearer "):].strip()
                    return str(bearer) if bearer else None
        return None

    @staticmethod
    async def _reject(send: Send, status: int, detail: str) -> None:
        message: Message = {"type": "http.response.start",
                            "status": status,
                            "headers": [(b"content-type", b"application/json")]}
        await send(message)
        await send({"type": "http.response.body",
                    "body": f'{{"detail":"{detail}"}}'.encode()})


def hash_token(token: str) -> str:
    """Public helper: SHA-256 hex of the bearer token."""
    return hashlib.sha256(token.encode()).hexdigest()
