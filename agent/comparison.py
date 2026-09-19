"""The space one person's entries are compared in.

One person's writing shares a voice. In the owner's first 156 imported entries a
single direction carried two-thirds of the variance, and the typical entry
scored 0.84 against the average of all of them. Compared raw, every theme
centroid looks like every entry: one theme cleared the 0.70 match bar for nearly
everything and took 121 of the 132 entries that grouped at all.

Removing the user's average compares entries on what *differs* between them
(ADR-0014). This lived inside PersistenceEngine, where clustering needed it.
Constructs need exactly the same space — a construct anchored in the owner's own
sentences would otherwise match every entry for the same reason — so it lives
here, used by both, rather than copied and left to drift.
"""

from __future__ import annotations

import numpy as np

from .constants import (
    PERSISTENCE_CLUSTER_THRESHOLD,
    PERSISTENCE_MATCH_THRESHOLD,
    PERSISTENCE_STYLE_CLUSTER_THRESHOLD,
    PERSISTENCE_STYLE_MATCH_THRESHOLD,
    PERSISTENCE_STYLE_MIN_ENTRIES,
)


class ComparisonSpace:
    """The shared voice to remove, and the thresholds that belong with it.

    How the style is *measured* is the caller's business. PersistenceEngine
    reads it through its own module boundary, which is where tests inject a
    synthetic journal; taking it as a function here keeps one seam instead of
    two that can disagree about which one is real.
    """

    def __init__(self, user_id: int, read_style=None):
        self.user_id = user_id
        self._read_style = read_style
        self._cache = None

    def invalidate(self) -> None:
        """Forget the measured voice.

        Rebuilding themes changes what evidence exists, so the average computed
        before it no longer describes the archive being regrouped.
        """
        self._cache = None

    def _style(self) -> tuple:
        """(count, mean) for this user — injected, or read from the database."""
        if self._read_style is not None:
            return self._read_style(self.user_id)
        from .database import db
        return db.get_evidence_style(self.user_id)

    def space(self) -> tuple:
        """(mean, match_threshold, cluster_threshold) for this user.

        Until there are PERSISTENCE_STYLE_MIN_ENTRIES the average is mostly the
        entries themselves, so raw comparison and its thresholds stand.
        """
        if self._cache is None:
            count, mean = self._style()
            if count >= PERSISTENCE_STYLE_MIN_ENTRIES and mean is not None:
                self._cache = (np.asarray(mean, dtype=np.float64),
                               PERSISTENCE_STYLE_MATCH_THRESHOLD,
                               PERSISTENCE_STYLE_CLUSTER_THRESHOLD)
            else:
                self._cache = (None, PERSISTENCE_MATCH_THRESHOLD,
                               PERSISTENCE_CLUSTER_THRESHOLD)
        return self._cache

    def project(self, vectors, are_centroids: bool = False) -> np.ndarray:
        """Unit vectors in the comparison space.

        An entry is normalised before the shared voice is removed; a centroid is
        not, because it is already an average of unit vectors and the shared
        voice is an average of the same kind. Anything with nothing left once
        the voice is removed projects to zero and matches nothing.
        """
        mean, _, _ = self.space()
        arr = np.atleast_2d(np.asarray(vectors, dtype=np.float64))
        if not are_centroids:
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            arr = arr / np.where(norms > 1e-12, norms, 1.0)
        if mean is not None:
            arr = arr - mean
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return np.where(norms > 1e-9, arr / np.where(norms > 1e-9, norms, 1.0), 0.0)
