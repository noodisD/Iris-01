"""Loopback serves the web UI; the TLS LAN listener serves /api to the paired phone's bearer."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings

# Pairing is approved on the laptop; the phone never manages its own bearer.
_LOOPBACK_ONLY = frozenset({
    ("GET", "/api/mobile/connection"),
    ("POST", "/api/mobile/pair"),
    ("POST", "/api/mobile/unpair"),
})

_last_rejection: dict[str, object] | None = None


def last_rejection() -> dict[str, object] | None:
    return _last_rejection


def forget_rejection() -> None:
    global _last_rejection  # noqa: PLW0603 - process-wide last refusal for the owner UI
    _last_rejection = None


class MobileAuthMiddleware:
    """Serve loopback freely; on the LAN listener admit only /api requests carrying the paired bearer."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        client_host = (scope.get("client") or ("", 0))[0]
        try:
            local_client = ipaddress.ip_address(client_host).is_loopback
        except ValueError:
            # Synthetic addresses used by in-process Starlette test transports,
            # never addresses a real TCP peer can present.
            local_client = client_host in {"testclient", "testserver"}

        if local_client and not scope.get("iris_lan"):
            await self.app(scope, receive, send)
            return

        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        method, path = scope.get("method", "POST"), scope.get("path", "")
        if not path.startswith("/api/") or (method, path) in _LOOPBACK_ONLY:
            await self._reject(send, 404, "not found")
            return
        if scope.get("scheme", "https") != "https":
            await self._reject(send, 403, "TLS required")
            return
        if not settings.LAN_BIND_ENABLED:
            await self._reject(send, 403, "lan bind disabled")
            return
        if not settings.MOBILE_BEARER_HASH:
            await self._reject(send, 503, "not paired")
            return
        token = self._extract_bearer(scope.get("headers") or [])
        if token is None or not hmac.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(), settings.MOBILE_BEARER_HASH
        ):
            await self._reject(send, 401, "invalid bearer")
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _extract_bearer(headers: list[tuple[bytes, bytes]]) -> str | None:
        authorizations = [value for name, value in headers if name.lower() == b"authorization"]
        if len(authorizations) != 1:
            return None
        text = authorizations[0].decode("latin-1")
        if not text.startswith("Bearer "):
            return None
        bearer = text[len("Bearer "):]
        return bearer if bearer and bearer == bearer.strip() else None

    @staticmethod
    async def _reject(send: Send, status: int, detail: str) -> None:
        global _last_rejection  # noqa: PLW0603 - process-wide last refusal for the owner UI
        if status != 404:
            _last_rejection = {
                "at": datetime.now(UTC).isoformat(),
                "status": status,
                "detail": detail,
            }
        message: Message = {"type": "http.response.start",
                            "status": status,
                            "headers": [(b"content-type", b"application/json")]}
        await send(message)
        await send({"type": "http.response.body",
                    "body": f'{{"detail":"{detail}"}}'.encode()})


def hash_token(token: str) -> str:
    """Public helper: SHA-256 hex of the bearer token."""
    return hashlib.sha256(token.encode()).hexdigest()
