"""Size caps and value rendering for stored telemetry.

Bookkeeping here must not raise into application code. Callers that cannot
tolerate a failure wrap the call; these functions themselves stay strict so a
bug in rendering is visible to that wrapper.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime

MAX_TEXT = 262_144
MAX_BODY = 65_536
MAX_SQL = 16_384
MAX_PARAM_STR = 4_096
MAX_STATUS = 4_096
VECTOR_MIN_LEN = 32


def render_text(value: str, limit: int) -> str:
    """Drop NULs (PostgreSQL rejects them) and cap length."""
    cleaned = value.replace("\x00", "")
    if len(cleaned) <= limit:
        return cleaned
    omitted = len(cleaned) - limit
    return cleaned[:limit] + f"… [truncated {omitted} chars]"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_vector(value: object) -> bool:
    """True for a long sequence of numbers, the shape of an embedding."""
    if isinstance(value, (list, tuple)):
        if len(value) < VECTOR_MIN_LEN:
            return False
        return all(_is_number(value[i]) for i in range(VECTOR_MIN_LEN))
    try:
        import numpy as np
    except ImportError:
        return False
    if not isinstance(value, np.ndarray):
        return False
    if value.ndim != 1 or len(value) < VECTOR_MIN_LEN:
        return False
    sample = value[:VECTOR_MIN_LEN].tolist()
    return all(_is_number(item) for item in sample)


def render_value(value: object) -> object:
    """A JSON-safe stand-in. Embeddings and bytes are summarised, not stored."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return render_text(value, MAX_PARAM_STR)
    if isinstance(value, (bytes, memoryview)):
        return f"<bytes len={len(value)}>"
    if is_vector(value):
        return f"<vector dim={len(value)}>"  # type: ignore[arg-type]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    adapted = getattr(value, "adapted", None)
    if type(value).__name__ == "Json" and adapted is not None:
        return render_value(adapted)
    if isinstance(value, Mapping):
        return {str(key): render_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [render_value(item) for item in value]
    return render_text(repr(value), 1_024)


def json_attr(value: object, limit: int) -> str:
    rendered = json.dumps(render_value(value), ensure_ascii=False, default=str)
    return render_text(rendered, limit)


def strip_nulls(value: str) -> str:
    return value.replace("\x00", "")
