"""Words that recur in the owner's sessions, and how they read in English.

A therapist has an idiolect: in Polish, "pole" can be a family's unspoken
climate, not a meadow. Without help, the English gloss renders such terms
literally, so an English question misses the passage. The
list lives on this machine only (`data/sessions/vocabulary.json`), never in the
repository, and feeds one place only: the English gloss used for search. It
never reaches chat or the reader, so no one's interpretations come in with it.
Without the file, the gloss is as before.

It is not given to Whisper as hotwords: on a real session that found no term
the plain run missed, and dropped two half-minute stretches of speech.

    {"terms": [{"pl": "pole", "en": "family field, not a meadow"}, ...]}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)


def vocabulary_path() -> Path:
    return Path(settings.DATA_DIR) / "sessions" / "vocabulary.json"


def terms() -> list[tuple[str, str]]:
    """(Polish, English) pairs, or none when the list is absent or unreadable."""
    path = vocabulary_path()
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return [(str(t["pl"]).strip(), str(t["en"]).strip()) for t in doc["terms"]
                if str(t["pl"]).strip() and str(t["en"]).strip()]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning(f"Session vocabulary unreadable ({type(exc).__name__}); not used")
        return []


def gloss_line() -> str:
    """One line for the translator, so each term reads the same way every time."""
    found = terms()
    if not found:
        return ""
    return "Render these recurring terms as given: " + "; ".join(f"{pl} → {en}" for pl, en in found) + "."
