"""How sensor bytes leave the device and arrive in IRIS.

The first transport is manual export (a file lands in data/sensors/).
Local-network pull and cloud mirror are deliberately not implemented —
they belong to a future ADR.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SyncTransport(ABC):
    """One pull of bytes from a sensor source. Stateless."""

    @abstractmethod
    def fetch(self, since: str | None = None) -> list[Path]:
        """Return paths to newly-arrived payloads, oldest first.

        ``since`` is an ISO timestamp string or None for "everything
        available". Implementations may ignore it; the contract is
        that nothing is fetched twice within a single process.
        """


class LocalExportTransport(SyncTransport):
    """Picks up files dropped in data/sensors/.

    The owner triggers a sync on the device; a file (or set of files)
    lands in the staging directory; this transport returns them in
    arrival order and leaves them in place — the service is responsible
    for moving them through review.
    """

    def __init__(self, staging_dir: Path) -> None:
        self._staging = Path(staging_dir)

    def fetch(self, since: str | None = None) -> list[Path]:
        return sorted(self._staging.glob("*"))


class HttpIntakeTransport(SyncTransport):
    """Sensor sync via HTTP POST to /api/mobile/sensor/intake.

    Used by the Android app: the phone assembles the JSON and POSTs it
    over the LAN bind (ADR-0018). This transport is the read side of
    the seam; the route's SensorService.stage_batch is the write side.
    ``fetch`` is a no-op because HTTP transport pushes rather than pulls;
    use ``push(payload)`` instead.
    """

    def __init__(self, intake_url: str, bearer_token: str) -> None:
        self._url = intake_url
        self._token = bearer_token

    def fetch(self, since: str | None = None) -> list[Path]:
        raise NotImplementedError(
            "HttpIntakeTransport pushes; it does not pull. "
            "Use HttpIntakeTransport.push(payload) instead.")

    def push(self, payload: dict) -> dict:
        """POST the PixelAdapter-shaped JSON to the intake route.

        Returns the parsed response dict. Raises RuntimeError on a
        non-2xx status so the caller can decide whether to retry.
        """
        import json as _json
        import urllib.request
        body = _json.dumps(payload).encode()
        req = urllib.request.Request(
            self._url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._token}"})
        with urllib.request.urlopen(req) as r:
            return _json.loads(r.read())
