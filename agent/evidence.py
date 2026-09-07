"""
Evidence Engine - Immutable Audit Layer

This module decouples analytics from explanation. It captures intermediate
metrics from engines and persists them as historical snapshots.
"""

import json
import logging
import uuid
from typing import Any

# Import database
from .database import evidence as evidence_repo

logger = logging.getLogger(__name__)

class EvidenceEngine:
    """
    Coordinates the recording and retrieval of structured evidence.
    """

    def record_evidence(
        self,
        engine_name: str,
        pattern_type: str,
        pattern_id: int,
        records: list[dict[str, Any]],
        related_pattern_id: int | None = None,
    ) -> uuid.UUID:
        """
        Persists a list of metrics as a single computation snapshot.

        Each record in 'records' should have:
        - type: str (e.g. 'count')
        - key: str (e.g. 'recent_count')
        - value: Any (JSON serializable)

        `related_pattern_id` is the other end of a pairwise relation — the
        target, for leverage and decision impact. Without it every target of one
        source shared a key, so the bundle returned for a pair could describe a
        different pair entirely.
        """
        comp_id = uuid.uuid4()

        db_rows = [
            (
                str(comp_id),
                pattern_type,
                pattern_id,
                related_pattern_id,
                engine_name,
                r['type'],
                r['key'],
                json.dumps(r['value'])
            )
            for r in records
        ]

        evidence_repo.add_records(db_rows)
        logger.info(f"Recorded {len(db_rows)} evidence rows for {engine_name} run {comp_id}")
        return comp_id

    def get_latest_bundle(self, pattern_type: str, pattern_id: int,
                          engine_name: str | None = None,
                          related_pattern_id: int | None = None) -> list[dict]:
        """
        Fetches the evidence for the most recent computation.

        For a pairwise engine, pass `related_pattern_id` to get the bundle for
        that relation rather than whichever of the source's relations ran last.
        """
        return evidence_repo.get_latest_bundle(
            pattern_type, pattern_id, engine_name, related_pattern_id
        )
