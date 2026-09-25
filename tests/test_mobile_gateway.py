"""The TLS mobile door admits the paired bearer to the API, never the web UI."""
import asyncio
import errno
import hashlib
import ssl
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import SubjectAlternativeName

from agent.config import Settings, settings
from agent.mobile_auth import hash_token
from iris_api import app
from scripts import serve_iris
from scripts.serve_iris import lan_app, prepare_certificate, tailnet_app


def test_host_rejects_wildcard_public_and_loopback():
    for host in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "::", "localhost", "100.128.0.1"):
        try:
            Settings(LAN_BIND_HOST=host, _env_file=None)
        except ValueError:
            continue
        raise AssertionError(f"accepted unsafe LAN host {host}")
    assert Settings(LAN_BIND_HOST="192.168.1.42", _env_file=None).LAN_BIND_HOST == "192.168.1.42"
    # The Tailscale range is private too (ADR-0022); 100.128.0.1 above is just past it.
    assert Settings(LAN_BIND_HOST="100.64.0.1", _env_file=None).LAN_BIND_HOST == "100.64.0.1"


def test_certificate_is_persistent_pinned_and_private(tmp_path: Path):
    cert, key, fingerprint = prepare_certificate("192.168.1.42", tmp_path)
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    assert stat.S_IMODE(cert.parent.stat().st_mode) == 0o700
    certificate = x509.load_pem_x509_certificate(cert.read_bytes())
    assert str(certificate.extensions.get_extension_for_class(SubjectAlternativeName)
               .value.get_values_for_type(x509.IPAddress)[0]) == "192.168.1.42"
    assert fingerprint == hashlib.sha256(certificate.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )).hexdigest()
    assert prepare_certificate("192.168.1.42", tmp_path) == (cert, key, fingerprint)
    cert2, key2, fingerprint2 = prepare_certificate("192.168.1.43", tmp_path)
    assert (cert2, key2) == (cert, key)
    reissued = x509.load_pem_x509_certificate(cert2.read_bytes())
    assert str(reissued.extensions.get_extension_for_class(SubjectAlternativeName)
               .value.get_values_for_type(x509.IPAddress)[0]) == "192.168.1.43"
    assert fingerprint2 == fingerprint
    assert certificate.not_valid_before_utc <= datetime.now(UTC) - timedelta(hours=23)
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))


def test_unavailable_lan_address_is_reported_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "LAN_LISTENER_ERROR", None)
    monkeypatch.setattr(settings, "LAN_URL", None)

    def unavailable(*_args):
        raise OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address")

    monkeypatch.setattr(serve_iris, "_socket", unavailable)
    assert asyncio.run(serve_iris._start_lan("192.168.1.42")) is None
    assert settings.LAN_URL is None
    assert f"192.168.1.42:{settings.LAN_BIND_PORT}" in settings.LAN_LISTENER_ERROR
    assert "Cannot assign requested address" in settings.LAN_LISTENER_ERROR


def test_lan_serves_the_api_only_to_the_paired_bearer_over_tls():
    async def exercise():
        transport = httpx.ASGITransport(app=lan_app, client=("127.0.0.1", 3456))
        async with httpx.AsyncClient(transport=transport, base_url="https://192.168.1.42") as client:
            bearer = {"Authorization": "Bearer " + "a" * 64}
            with patch.object(settings, "LAN_BIND_ENABLED", False), patch.object(
                settings, "MOBILE_BEARER_HASH", None
            ):
                assert (await client.get("/api/mobile/status", headers=bearer)).status_code == 403
            with patch.object(settings, "LAN_BIND_ENABLED", True), patch.object(
                settings, "MOBILE_BEARER_HASH", None
            ):
                assert (await client.get("/api/mobile/status", headers=bearer)).status_code == 503
            with patch.object(settings, "LAN_BIND_ENABLED", True), patch.object(
                settings, "MOBILE_BEARER_HASH", hash_token("a" * 64)
            ):
                assert (await client.get("/api/mobile/status")).status_code == 401
                assert (await client.get("/api/mobile/status", headers={
                    "Authorization": "Bearer " + "b" * 64
                })).status_code == 401
                response = await client.get("/api/mobile/status", headers=bearer)
                assert response.json() == {"status": "connected"}
                for path in ("/", "/health", "/assets/index.js", "/api/mobile/connection",
                             "/api/mobile/status/extra"):
                    assert (await client.get(path, headers=bearer)).status_code == 404
                assert (await client.post("/api/mobile/pair", headers=bearer)).status_code == 404
                assert (await client.post("/api/mobile/unpair", headers=bearer)).status_code == 404
                batches = await client.get("/api/sensors/batches", headers=bearer)
                assert batches.status_code == 200
                assert isinstance(batches.json(), list)
                assert (await client.get("/api/sensors/batches")).status_code == 401
                assert (await client.get("/api/sensors/batches", headers={
                    "Authorization": "Bearer " + "b" * 64
                })).status_code == 401
                assert (await client.post("/api/mobile/sensor/intake", headers=bearer,
                                          json={"device": "unknown"})).status_code == 400
        # Unintended HTTP bind can neither serve the web UI nor receive a bearer.
        plain = httpx.ASGITransport(app=lan_app, client=("192.168.1.42", 3456))
        async with httpx.AsyncClient(transport=plain, base_url="http://192.168.1.42") as client:
            with patch.object(settings, "LAN_BIND_ENABLED", True), patch.object(
                settings, "MOBILE_BEARER_HASH", hash_token("a" * 64)
            ):
                assert (await client.get("/api/mobile/status", headers=bearer)).status_code == 403
                assert (await client.get("/api/sensors/batches", headers=bearer)).status_code == 403
        local = httpx.ASGITransport(app=app, client=("127.0.0.1", 3456))
        async with httpx.AsyncClient(transport=local, base_url="http://127.0.0.1") as client:
            assert (await client.get("/api/mobile/connection")).status_code == 200
    asyncio.run(exercise())


def test_connection_reports_phone_contact_and_last_rejection():
    async def exercise():
        transport = httpx.ASGITransport(app=lan_app, client=("192.168.1.50", 3456))
        async with httpx.AsyncClient(transport=transport, base_url="https://192.168.1.42") as client:
            with patch.object(settings, "LAN_BIND_ENABLED", True), patch.object(
                settings, "MOBILE_BEARER_HASH", hash_token("a" * 64)
            ):
                bad = await client.get("/api/mobile/status", headers={
                    "Authorization": "Bearer " + "b" * 64,
                })
                assert bad.status_code == 401
                good = await client.get("/api/mobile/status", headers={
                    "Authorization": "Bearer " + "a" * 64,
                })
                assert good.status_code == 200
                local = httpx.ASGITransport(app=app, client=("127.0.0.1", 3456))
                async with httpx.AsyncClient(transport=local, base_url="http://127.0.0.1") as ui:
                    connection = (await ui.get("/api/mobile/connection")).json()
                    assert connection["last_rejection"]["status"] == 401
                    assert connection["last_seen_at"] is not None
    asyncio.run(exercise())


def test_remote_browser_cannot_change_mobile_pairing():
    async def exercise():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 3456))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            headers = {"Origin": "https://untrusted.example"}
            pair = await client.post("/api/mobile/pair", headers=headers, json={"token": "a" * 64})
            unpair = await client.post("/api/mobile/unpair", headers=headers)
            assert pair.status_code == unpair.status_code == 403
            local = {"Origin": "http://127.0.0.1:5173"}
            assert (await client.post("/api/mobile/pair", headers=local,
                                      json={"token": "a" * 64})).status_code == 200
            assert (await client.post("/api/mobile/unpair", headers=local)).status_code == 200
    asyncio.run(exercise())


def test_remote_browser_cannot_stage_mobile_data():
    async def exercise():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 3456))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            response = await client.post("/api/mobile/sensor/intake",
                                         headers={"Origin": "https://untrusted.example"},
                                         json={"device": "Pixel 10a", "tiers": {}})
            assert response.status_code == 403
    asyncio.run(exercise())


def test_the_tailnet_door_admits_only_the_owner_through_the_real_app():
    async def exercise():
        transport = httpx.ASGITransport(app=tailnet_app, client=("127.0.0.1", 3456))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8001") as client:
            owner = {"Tailscale-User-Login": "owner@example.com"}
            with patch.object(settings, "TAILNET_OWNERS", "owner@example.com"):
                assert (await client.get("/api/mobile/status", headers=owner)).status_code == 200
                assert (await client.get("/api/mobile/status")).status_code == 403
                assert (await client.get("/api/mobile/status", headers={
                    "Tailscale-User-Login": "guest@example.com"})).status_code == 403
                assert (await client.get("/api/mobile/connection", headers=owner)).status_code == 404
            with patch.object(settings, "TAILNET_OWNERS", ""):
                assert (await client.get("/api/mobile/status", headers=owner)).status_code == 403
    asyncio.run(exercise())
