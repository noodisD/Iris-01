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
