"""Who may reach IRIS, through which of its three doors.

Loopback serves the web UI to the laptop; the TLS LAN listener serves /api to
the paired phone's bearer; the tailnet door serves the owner's Tailscale login
(ADR-0022).

The web doors authenticate the *device*, not the page, so a browser on it will
carry a request from any website to them. Two rules keep other sites out:
the Host must be IRIS's own name, which defeats DNS rebinding (a hostile name
re-pointed at 127.0.0.1 would otherwise let its page read every response), and
a request that changes anything must come from IRIS's own page, which defeats
cross-site form posts. Requests with no browser headers, from curl, scripts or
tests, are unaffected: no browser can send those.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings

# Pairing is approved on the laptop; the phone never manages its own bearer.
_LOOPBACK_ONLY = frozenset({
    ("GET", "/api/mobile/connection"),
    ("POST", "/api/mobile/pair"),
    ("POST", "/api/mobile/unpair"),
})

#: Of those, what stays off the tailnet door: minting or revoking the phone's
#: bearer. The connection view carries no secret and feeds the address QR.
_LAPTOP_ONLY = frozenset({
    ("POST", "/api/mobile/pair"),
    ("POST", "/api/mobile/unpair"),
})

#: Set by `tailscale serve` to the connecting user's login (ADR-0022).
_TAILNET_LOGIN = b"tailscale-user-login"

#: The names the laptop's own browser uses for the loopback door.
_LOCAL_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})

#: Methods that only read. Everything else must come from IRIS's own page.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_last_rejection: dict[str, object] | None = None


def _header_values(scope: Scope, name: bytes) -> list[str]:
    return [value.decode("latin-1") for key, value in scope.get("headers") or []
            if key.lower() == name]


def _one_header(scope: Scope, name: bytes) -> str | None:
    """The header's value; None when absent. Repeated copies read as ''."""
    values = _header_values(scope, name)
    return values[0] if len(values) == 1 else ("" if values else None)


def _authority(value: str, default_port: int) -> tuple[str, int] | None:
    """`host[:port]` as (lower-case name, port), or None when unparseable."""
    try:
        parts = urlsplit("//" + value)
        name, port = parts.hostname, parts.port
    except ValueError:
        return None
    if not name or parts.username is not None or parts.path or parts.query:
        return None
    return name.lower(), port or default_port


def _origin(value: str) -> tuple[str, str, int] | None:
    """An Origin header as (scheme, name, port); None for "null" or garbage."""
    try:
        parts = urlsplit(value)
        name, port = parts.hostname, parts.port
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not name or parts.path not in {"", "/"}:
        return None
    return parts.scheme, name.lower(), port or (443 if parts.scheme == "https" else 80)


def _cross_site(scope: Scope, allowed) -> bool:
    """Whether a browser sent this state-changing request from another site.

    `allowed(scheme, name, port)` says which page origins are IRIS's own.
    Sec-Fetch-Site is checked too, because it is set by the browser on every
    request and a page cannot suppress it.
    """
    if scope.get("method", "GET") in _SAFE_METHODS:
        return False
    fetch_site = _one_header(scope, b"sec-fetch-site")
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        return True
    origin = _one_header(scope, b"origin")
    if origin is None:
        return False
    parsed = _origin(origin)
    return parsed is None or not allowed(*parsed)


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

        # Place coordinates and Timeline exports stay on the laptop. A paired
        # phone may read coordinate-free day summaries, not these owner routes.
        path = scope.get("path", "")
        if (scope["type"] == "http" and
                (scope.get("iris_tailnet") or scope.get("iris_lan") or not local_client) and
                (path == "/api/places" or path.startswith("/api/places/")
                 or path == "/api/sensors/import/google-timeline")):
            await self._reject(send, 404, "not found")
            return
        if scope.get("iris_tailnet"):
            await self._tailnet(scope, receive, send)
            return

        if local_client and not scope.get("iris_lan"):
            if _header_values(scope, _TAILNET_LOGIN):
                # `tailscale serve` pointed at the plain loopback door, where
                # the owner check does not run. Only TAILNET_PORT admits it.
                await self._refuse(scope, send, "tailnet requests use the tailnet door")
                return
            names = _LOCAL_NAMES | ({"testserver"} if client_host == "testclient" else set())
            host = _one_header(scope, b"host")
            if host is not None and (_authority(host, 80) or ("", 0))[0] not in names:
                await self._refuse(scope, send, "unknown host")
                return
            if _cross_site(scope, lambda _scheme, name, _port: name in names):
                await self._refuse(scope, send, "cross-site request refused")
                return
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

    async def _tailnet(self, scope: Scope, receive: Receive, send: Send) -> None:
        """The door `tailscale serve` targets: the owner's login, or nothing.

        `serve` sets the login header from the connecting device's identity and
        drops any copy the client sent. A request without exactly one, such as
        one from a tagged device, which carries no user, is refused, as is
        every request when no owner is configured.
        """
        logins = _header_values(scope, _TAILNET_LOGIN)
        owners = settings.tailnet_owners
        if len(logins) != 1 or not owners or logins[0].strip().lower() not in owners:
            await self._refuse(scope, send, "not the owner's tailnet login")
            return
        if (scope.get("method", "POST"), scope.get("path", "")) in _LAPTOP_ONLY:
            # Pairing hands out the phone's credentials: laptop only.
            await self._reject(send, 404, "not found")
            return
        # `serve` passes the browser's Host through unchanged, and its TLS
        # certificate names only this machine, so a rebound name cannot reach
        # here. The page's own origin is therefore https://<Host>.
        host = _authority(_one_header(scope, b"host") or "", 443)
        if _cross_site(scope, lambda scheme, name, port:
                       scheme == "https" and host is not None and (name, port) == host):
            await self._refuse(scope, send, "cross-site request refused")
            return
        await self.app(scope, receive, send)

    @classmethod
    async def _refuse(cls, scope: Scope, send: Send, detail: str) -> None:
        """A 403 for the browser doors. Not recorded: Settings' "last refused
        phone request" is about the phone, and a refused web page is not."""
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await cls._reject(send, 403, detail, record=False)

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
    async def _reject(send: Send, status: int, detail: str, *, record: bool = True) -> None:
        global _last_rejection  # noqa: PLW0603 - process-wide last refusal for the owner UI
        if record and status != 404:
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
