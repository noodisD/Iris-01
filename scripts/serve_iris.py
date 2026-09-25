"""Run the local web API and, when configured, its pinned-HTTPS mobile door.

Run from the checkout with `uv run python scripts/serve_iris.py`. The ordinary
`uvicorn iris_api:app --host 127.0.0.1` remains a loopback-only alternative.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import os
import socket
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.config import settings  # noqa: E402
from iris_api import app  # noqa: E402

LOG = logging.getLogger("uvicorn.error")


def _atomic_private_file(path: Path, contents: bytes) -> None:
    """Replace a PEM within the private directory, never leaving a partial file."""
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".mobile-")
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(contents)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_or_create_key(path: Path) -> ec.EllipticCurvePrivateKey:
    if path.exists():
        path.chmod(0o600)
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("mobile private key is not an EC key")
        return key
    key = ec.generate_private_key(ec.SECP256R1())
    _atomic_private_file(path, key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    return key


def prepare_certificate(host: str, data_dir: Path) -> tuple[Path, Path, str]:
    """Reuse the server key, issuing a certificate only when absent or its IP changed."""
    # Also validate when called directly instead of trusting Settings initialization.
    host = settings.validate_lan_host(host)
    if not host:
        raise ValueError("LAN_BIND_HOST must be explicitly configured")
    mobile_dir = data_dir / "mobile"
    if mobile_dir.is_symlink():
        raise ValueError("mobile certificate directory must not be a symlink")
    mobile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    mobile_dir.chmod(0o700)
    cert_path, key_path = mobile_dir / "cert.pem", mobile_dir / "key.pem"
    if cert_path.is_symlink() or key_path.is_symlink():
        raise ValueError("mobile certificate files must not be symlinks")
    if cert_path.exists() and not key_path.exists():
        raise ValueError("mobile certificate exists without its private key")

    key = _load_or_create_key(key_path)

    certificate = None
    if cert_path.exists():
        cert_path.chmod(0o600)
        certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
        if certificate.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ) != key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ):
            raise ValueError("mobile certificate does not match its private key")

    address = ipaddress.IPv4Address(host)
    now = datetime.now(UTC)
    needs_certificate = certificate is None
    if certificate is not None:
        try:
            names = certificate.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value.get_values_for_type(x509.IPAddress)
        except x509.ExtensionNotFound:
            names = []
        needs_certificate = (
            names != [address] or certificate.not_valid_after_utc <= now
            or certificate.not_valid_before_utc > now
        )
    if needs_certificate:
        identity = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "IRIS Mobile")])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(identity).issuer_name(identity).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(address)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        _atomic_private_file(cert_path, certificate.public_bytes(serialization.Encoding.PEM))
    pin = hashlib.sha256(key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )).hexdigest()
    return cert_path, key_path, pin


class LanServer(uvicorn.Server):
    """Only the loopback server owns process signal handling and app lifespan."""

    @contextmanager
    def capture_signals(self):
        yield

    def install_signal_handlers(self):  # compatibility with older uvicorn
        pass


async def lan_app(scope, receive, send):
    # Even a process on this machine that connects via the LAN address must
    # pass the mobile route allow-list and bearer check.
    if scope["type"] in {"http", "websocket"}:
        scope = {**scope, "iris_lan": True}
    await app(scope, receive, send)


def _socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(socket.SOMAXCONN)
        sock.setblocking(False)
        return sock
    except BaseException:
        sock.close()
        raise


async def _started(server: uvicorn.Server, task: asyncio.Task) -> None:
    while not server.started:
        if task.done():
            await task
            raise RuntimeError("IRIS listener exited before it could start")
        await asyncio.sleep(0.02)


def _lan_unavailable(host: str, port: int, error: BaseException | None) -> None:
    settings.LAN_URL = None
    settings.LAN_PUBLIC_KEY_SHA256 = None
    reason = f"{type(error).__name__}: {error}" if error else "it stopped unexpectedly"
    settings.LAN_LISTENER_ERROR = f"The phone listener could not use {host}:{port}: {reason}"
    LOG.warning("%s. The web UI keeps running on 127.0.0.1:8000.", settings.LAN_LISTENER_ERROR)


async def _start_lan(host: str) -> tuple[LanServer, asyncio.Task, socket.socket] | None:
    port = settings.LAN_BIND_PORT
    lan_socket = None
    server = None
    task = None
    try:
        directory = Path(settings.DATA_DIR)
        if not directory.is_absolute():
            directory = ROOT / directory
        cert_path, key_path, pin = prepare_certificate(host, directory)
        lan_socket = _socket(host, port)
        server = LanServer(uvicorn.Config(
            lan_app, host=host, port=port, lifespan="off",
            ssl_certfile=str(cert_path), ssl_keyfile=str(key_path), proxy_headers=False,
        ))
        task = asyncio.create_task(server.serve(sockets=[lan_socket]))
        try:
            await _started(server, task)
        except Exception:
            server.should_exit = True
            await asyncio.gather(task, return_exceptions=True)
            raise
    except Exception as exc:
        if lan_socket is not None:
            lan_socket.close()
        _lan_unavailable(host, port, exc)
        return None
    settings.LAN_LISTENER_ERROR = None
    settings.LAN_PUBLIC_KEY_SHA256 = pin
    settings.LAN_URL = f"https://{host}:{port}"
    LOG.info(
        "Phone listener: %s (server key SHA-256 %s). "
        "The laptop firewall must allow TCP %d from the phone's Wi-Fi.",
        settings.LAN_URL, pin, port,
    )
    return server, task, lan_socket


async def serve() -> None:
    host = settings.LAN_BIND_HOST
    loopback_socket = _socket("127.0.0.1", 8000)
    loopback = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=8000, proxy_headers=False,
    ))
    local_task = asyncio.create_task(loopback.serve(sockets=[loopback_socket]))
    lan = lan_task = lan_socket = None
    try:
        await _started(loopback, local_task)
        if host:
            started = await _start_lan(host)
            if started is not None:
                lan, lan_task, lan_socket = started
        if lan_task is not None:
            done, _ = await asyncio.wait(
                {local_task, lan_task}, return_when=asyncio.FIRST_COMPLETED,
            )
            if lan_task in done and local_task not in done:
                _lan_unavailable(
                    host, settings.LAN_BIND_PORT,
                    lan_task.exception() if not lan_task.cancelled() else None,
                )
                lan_socket.close()
        await local_task
    finally:
        settings.LAN_URL = None
        settings.LAN_PUBLIC_KEY_SHA256 = None
        loopback.should_exit = True
        if lan is not None:
            lan.should_exit = True
        await asyncio.gather(local_task, *([lan_task] if lan_task else []), return_exceptions=True)
        loopback_socket.close()
        if lan_socket is not None:
            lan_socket.close()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
