"""Bearer-token middleware for the LAN bind.

Loopback bypasses; everything else needs the bearer. The token is
stored as a SHA-256 hash; the phone stores the raw token in the
Android Keystore.
"""
import hashlib
import unittest
from contextlib import ExitStack
from unittest.mock import patch

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _run_middleware(mw, scope):
    """Drive the ASGI middleware synchronously for testing.

    Starlette middleware is constructed with `mw(app=downstream)`; the
    resulting instance is callable with (scope, receive, send). We
    wrap a downstream callable in a closure and pass it as the
    constructor arg, then call mw(scope, receive, send).
    """
    sent: list[dict] = []
    called_next = {"v": False}

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    async def downstream_app(scope, receive, send):
        called_next["v"] = True

    # Rebind the middleware to use our test downstream.
    mw.app = downstream_app

    import asyncio
    asyncio.run(mw(scope, receive, send))
    return sent, called_next["v"]


class HashTests(unittest.TestCase):
    def test_hash_is_deterministic(self):
        self.assertEqual(_hash("abc"), _hash("abc"))

    def test_hash_is_64_hex_chars(self):
        h = _hash("abc")
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


class MiddlewareTests(unittest.TestCase):
    """Drives the middleware directly; FastAPI TestClient wiring is Task 3."""

    def _build_middleware(self):
        from agent.mobile_auth import MobileAuthMiddleware
        # The middleware's __init__ takes an `app`; we don't need it for
        # direct ASGI driving because we exercise the inner method by
        # constructing the class and calling __call__.
        return MobileAuthMiddleware(app=None)  # type: ignore[arg-type]

    def _patched_settings(self, **overrides):
        """Return a context manager that sets overrides on the live settings.

        The middleware module reads its `settings` from the module
        namespace; we patch those names directly.
        """
        from agent import mobile_auth as mod
        defaults = {
            "LAN_BIND_ENABLED": True,
            "MOBILE_BEARER_HASH": _hash("secret-token"),
        }
        defaults.update(overrides)
        stack = ExitStack()
        for k, v in defaults.items():
            stack.enter_context(patch.object(mod.settings, k, v))
        return stack

    def test_loopback_request_passes_without_bearer(self):
        mw = self._build_middleware()
        with self._patched_settings():
            scope = {"type": "http", "client": ("127.0.0.1", 12345),
                     "headers": [], "path": "/api/mobile/sensor/intake"}
            _, called = _run_middleware(mw, scope)
            self.assertTrue(called)

    def test_ipv6_loopback_request_passes_without_bearer(self):
        mw = self._build_middleware()
        with self._patched_settings():
            scope = {"type": "http", "client": ("::1", 12345),
                     "headers": [], "path": "/api/mobile/sensor/intake"}
            _, called = _run_middleware(mw, scope)
            self.assertTrue(called)

    def test_lan_request_without_bearer_is_401(self):
        mw = self._build_middleware()
        with self._patched_settings():
            scope = {"type": "http", "client": ("192.168.1.42", 12345),
                     "headers": [], "path": "/api/mobile/sensor/intake"}
            sent, called = _run_middleware(mw, scope)
            self.assertFalse(called)
            self.assertEqual(sent[0]["status"], 401)

    def test_lan_request_with_correct_bearer_passes(self):
        mw = self._build_middleware()
        with self._patched_settings():
            scope = {"type": "http", "client": ("192.168.1.42", 12345),
                     "headers": [(b"authorization", b"Bearer secret-token")],
                     "path": "/api/mobile/sensor/intake"}
            _, called = _run_middleware(mw, scope)
            self.assertTrue(called)

    def test_lan_request_with_wrong_bearer_is_401(self):
        mw = self._build_middleware()
        with self._patched_settings():
            scope = {"type": "http", "client": ("192.168.1.42", 12345),
                     "headers": [(b"authorization", b"Bearer wrong-token")],
                     "path": "/api/mobile/sensor/intake"}
            sent, called = _run_middleware(mw, scope)
            self.assertFalse(called)
            self.assertEqual(sent[0]["status"], 401)

    def test_disabled_lan_bind_rejects_lan_requests_even_with_bearer(self):
        # Belt-and-braces: if the bind is disabled, the middleware
        # rejects LAN requests outright. The bind shouldn't be live.
        mw = self._build_middleware()
        with self._patched_settings(LAN_BIND_ENABLED=False):
            scope = {"type": "http", "client": ("192.168.1.42", 12345),
                     "headers": [(b"authorization", b"Bearer secret-token")],
                     "path": "/api/mobile/sensor/intake"}
            sent, called = _run_middleware(mw, scope)
            self.assertFalse(called)
            self.assertEqual(sent[0]["status"], 403)

    def test_no_bearer_configured_returns_503(self):
        # The bind is enabled but the owner has not paired yet. The
        # middleware returns 503, not 401, so the phone can tell
        # "not paired" apart from "wrong token".
        mw = self._build_middleware()
        with self._patched_settings(MOBILE_BEARER_HASH=None):
            scope = {"type": "http", "client": ("192.168.1.42", 12345),
                     "headers": [], "path": "/api/mobile/sensor/intake"}
            sent, called = _run_middleware(mw, scope)
            self.assertFalse(called)
            self.assertEqual(sent[0]["status"], 503)


class TailnetDoorTests(unittest.TestCase):
    """`tailscale serve` reaches IRIS through its own loopback door (ADR-0022).

    Every request there looks local, so the connecting user's login, which
    `serve` sets and clients cannot forge, is all that tells the owner apart
    from anyone else on the tailnet.
    """

    OWNER = "owner@example.com"

    def _run(self, headers, path="/api/decisions", method="GET", owners=OWNER,
             tailnet=True, kind="http"):
        from agent import mobile_auth as mod
        mw = mod.MobileAuthMiddleware(app=None)  # type: ignore[arg-type]
        scope = {"type": kind, "client": ("127.0.0.1", 50000), "method": method,
                 "path": path, "headers": headers}
        if tailnet:
            scope["iris_tailnet"] = True
        with patch.object(mod.settings, "TAILNET_OWNERS", owners):
            return _run_middleware(mw, scope)

    @staticmethod
    def _login(value):
        return [(b"tailscale-user-login", value.encode())]

    def test_the_owners_login_is_let_in(self):
        _, called = self._run(self._login(self.OWNER))
        self.assertTrue(called)

    def test_the_login_is_compared_without_case(self):
        _, called = self._run(self._login("Owner@Example.com"))
        self.assertTrue(called)

    def test_another_login_is_refused(self):
        sent, called = self._run(self._login("guest@example.com"))
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 403)

    def test_no_login_is_refused(self):
        # A tagged device carries no user, and must not look like the laptop.
        sent, called = self._run([])
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 403)

    def test_two_logins_are_refused(self):
        sent, called = self._run(self._login(self.OWNER) + self._login("guest@example.com"))
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 403)

    def test_nobody_is_let_in_when_no_owner_is_configured(self):
        sent, called = self._run(self._login(self.OWNER), owners="")
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 403)

    def test_one_of_several_owners_is_let_in(self):
        _, called = self._run(self._login(self.OWNER), owners="other@example.com, owner@example.com")
        self.assertTrue(called)

    def test_pairing_stays_on_the_laptop(self):
        for method, path in [("GET", "/api/mobile/connection"), ("POST", "/api/mobile/pair"),
                             ("POST", "/api/mobile/unpair")]:
            sent, called = self._run(self._login(self.OWNER), path=path, method=method)
            self.assertFalse(called, path)
            self.assertEqual(sent[0]["status"], 404, path)

    def test_the_web_app_itself_is_served(self):
        _, called = self._run(self._login(self.OWNER), path="/")
        self.assertTrue(called)

    def test_a_websocket_from_another_login_is_closed(self):
        sent, called = self._run(self._login("guest@example.com"), kind="websocket")
        self.assertFalse(called)
        self.assertEqual(sent[0], {"type": "websocket.close", "code": 1008})

    def test_serve_pointed_at_the_plain_door_is_refused(self):
        # The owner check runs only on the tailnet door; a login header on the
        # ordinary loopback door means `serve` was aimed at the wrong port.
        sent, called = self._run(self._login(self.OWNER), tailnet=False)
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 403)

    def test_the_laptop_is_unchanged(self):
        _, called = self._run([], tailnet=False, owners="")
        self.assertTrue(called)


class LifespanLoadTests(unittest.TestCase):
    """The lifespan must load the pairing row into in-process settings.

    Without this, the bearer middleware rejects every LAN request
    after a server restart, even though the phone is still paired.
    """

    def test_lifespan_loads_pairing_into_settings(self):
        from agent.database import db
        from agent.config import settings as cfg
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE mobile_pairing;")
            cur.execute(
                "INSERT INTO mobile_pairing (id, bearer_hash, lan_bind_enabled) "
                "VALUES (1, %s, true)",
                ("x" * 64,))
            conn.commit()
        cfg.MOBILE_BEARER_HASH = None
        cfg.LAN_BIND_ENABLED = False

        # Drive the lifespan startup path directly. The function is a
        # context manager: enter it, observe settings, exit without
        # running the rest of the route table.
        import asyncio
        from iris_api import lifespan
        cm = lifespan(None)  # type: ignore[arg-type]
        asyncio.run(cm.__aenter__())
        try:
            self.assertEqual(cfg.MOBILE_BEARER_HASH, "x" * 64)
            self.assertTrue(cfg.LAN_BIND_ENABLED)
        finally:
            asyncio.run(cm.__aexit__(None, None, None))
        # Clean up so the rest of the suite is unaffected.
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE mobile_pairing;")
            cur.execute(
                "INSERT INTO mobile_pairing (id) VALUES (1);")
            conn.commit()
        cfg.MOBILE_BEARER_HASH = None
        cfg.LAN_BIND_ENABLED = False


class PairingEndpointTests(unittest.TestCase):
    def setUp(self):
        from agent.database import db
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE mobile_pairing;")
            cur.execute(
                "INSERT INTO mobile_pairing (id) VALUES (1);")
            conn.commit()
        from agent import config as cfg
        cfg.settings.MOBILE_BEARER_HASH = None
        cfg.settings.LAN_BIND_ENABLED = False

    def tearDown(self):
        from agent import config as cfg
        cfg.settings.MOBILE_BEARER_HASH = None
        cfg.settings.LAN_BIND_ENABLED = False

    def test_pair_stores_hash_and_enables_bind(self):
        from fastapi.testclient import TestClient
        from iris_api import app
        from agent import config as cfg
        from agent.database import db as database
        with TestClient(app) as client:
            r = client.post("/api/mobile/pair",
                            json={"token": "a" * 64,
                                  "lan_bind_enabled": True})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(cfg.settings.LAN_BIND_ENABLED)
            self.assertIsNotNone(cfg.settings.MOBILE_BEARER_HASH)
            self.assertEqual(len(cfg.settings.MOBILE_BEARER_HASH), 64)
            # Verify the row in the database matches the in-process setting.
            with database.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT bearer_hash, lan_bind_enabled FROM mobile_pairing "
                    "WHERE id = 1")
                row = cur.fetchone()
                self.assertEqual(row[0], cfg.settings.MOBILE_BEARER_HASH)
                self.assertTrue(row[1])

    def test_pair_rejects_short_tokens(self):
        from fastapi.testclient import TestClient
        from iris_api import app
        with TestClient(app) as client:
            r = client.post("/api/mobile/pair",
                            json={"token": "short",
                                  "lan_bind_enabled": True})
            self.assertEqual(r.status_code, 400)

    def test_pair_requires_256_bit_token_and_boolean_gate(self):
        from fastapi.testclient import TestClient
        from iris_api import app
        with TestClient(app) as client:
            for token in ("x" * 64, "a" * 63, "a" * 65):
                self.assertEqual(
                    client.post("/api/mobile/pair",
                                json={"token": token, "lan_bind_enabled": True}).status_code,
                    400,
                )
            self.assertEqual(
                client.post("/api/mobile/pair",
                            json={"token": "a" * 64, "lan_bind_enabled": "false"}).status_code,
                400,
            )

    def test_unpair_revokes_persisted_and_live_pairing(self):
        from fastapi.testclient import TestClient
        from iris_api import app
        from agent.database import db
        from agent.config import settings
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/mobile/pair", json={
                "token": "a" * 64, "lan_bind_enabled": True,
            }).status_code, 200)
            self.assertTrue(client.get("/api/mobile/connection").json()["paired"])
            self.assertEqual(client.post("/api/mobile/unpair").json(), {"status": "unpaired"})
            self.assertFalse(client.get("/api/mobile/connection").json()["paired"])
            self.assertFalse(settings.LAN_BIND_ENABLED)
            self.assertIsNone(settings.MOBILE_BEARER_HASH)
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT bearer_hash, lan_bind_enabled FROM mobile_pairing WHERE id = 1")
                self.assertEqual(cur.fetchone(), (None, False))


if __name__ == "__main__":
    unittest.main()
