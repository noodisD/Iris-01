"""
Evidence Engine - Immutable Audit Layer

This module decouples analytics from explanation. It captures intermediate
metrics from engines and persists them as historical snapshots.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

# Import database
from .database import db

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
        records: List[Dict[str, Any]]
    ) -> uuid.UUID:
        """
        Persists a list of metrics as a single computation snapshot.
        
        Each record in 'records' should have:
        - type: str (e.g. 'count')
        - key: str (e.g. 'recent_count')
        - value: Any (JSON serializable)
        """
        comp_id = uuid.uuid4()
        
        db_rows = [
            (
                str(comp_id),
                pattern_type,
                pattern_id,
                engine_name,
                r['type'],
                r['key'],
                json.dumps(r['value'])
            )
            for r in records
        ]
        
        db.add_evidence_records(db_rows)
        logger.info(f"Recorded {len(db_rows)} evidence rows for {engine_name} run {comp_id}")
        return comp_id

    def get_latest_bundle(self, pattern_type: str, pattern_id: int, engine_name: Optional[str] = None) -> List[Dict]:
        """
        Fetches the evidence for the most recent computation.
        """
        return db.get_latest_evidence_bundle(pattern_type, pattern_id, engine_name)
