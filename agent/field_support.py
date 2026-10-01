"""Diagnostic adapter for the exact contextual field check used by live discovery.

The original source-selecting checker is in connections.check_account_fields.
This module adds only unavailable verdicts for evaluation when that semantic
request fails; unavailable is never not_stated or a successful empty read.
"""

from __future__ import annotations

import logging

from .connections import check_account_fields
from .dynamics import validate_field_checks
from .episodes import Episode, GROUNDED_FIELDS, ReadUnavailable
from .reading_version import VERIFIED_READER_VERSION
from .reference_evaluation import CHECKED

logger = logging.getLogger(__name__)
VERIFICATION_VERSION = VERIFIED_READER_VERSION
VERDICTS = ("supported", "not_stated", "contradicted", "unclear", "unavailable")


def check(episode: dict | Episode, intelligence) -> dict[str, str]:
    """Use production source selection; keep operational failure separate."""
    account = Episode.from_dict(episode) if isinstance(episode, dict) else episode
    if not isinstance(account, Episode):
        raise ValueError("invalid v4 account")
    fields = {field for field in GROUNDED_FIELDS if getattr(account, field) is not None}
    if not fields:
        return {}
    if intelligence is None:
        return dict.fromkeys(fields, "unavailable")
    try:
        result = check_account_fields(account, intelligence)
        validate_field_checks(account, result)
    except (ReadUnavailable, ValueError) as exc:
        logger.error("Field support unavailable (%s)", type(exc).__name__)
        return dict.fromkeys(fields, "unavailable")
    return {row.field: row.verdict for row in result.checks}


def tally(results: list[dict]) -> dict[str, dict[str, int]]:
    counts = {field: dict.fromkeys(VERDICTS, 0) for field in CHECKED}
    for result in results:
        for field, verdict in result["verdicts"].items():
            if field not in counts or verdict not in VERDICTS:
                raise ValueError("invalid diagnostic field verdict")
            counts[field][verdict] += 1
    return counts
