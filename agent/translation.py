"""An English version of a record written in another language (ADR-0036).

The owner reads and asks in English, and almost all of the archive is English;
the sessions are Polish. So a record in another language keeps its original
and gains one stored English version, which is what the reader, chat and the
journal use. The original stays the record: it is never changed, the journal
shows it one tap away, and an edit to it throws the translation away.

A session is translated turn by turn and kept in the session format, with the
same speakers and times, so everything that asks "whose words are these?"
(`sessions.owner_turn`) gets the same answer from the English as from the
Polish. A quote from the English is a translation, and is checked word for
word against the English of the owner's own turns.

The worker model translates; a translation that does not come back whole
(a turn missing, or one far longer or shorter than its original) is not kept,
and the record is read in its own language as before.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .config import settings
from .database import db

logger = logging.getLogger(__name__)

#: Turns sent at once: enough context for pronouns and who is who, small enough
#: that a reply stays well inside the output limit.
TURNS_PER_CALL = 20
#: Characters of plain text sent at once.
CHARS_PER_CALL = 6000
#: English from Polish runs a little longer or shorter; outside this, a turn
#: was summarised or padded, not translated.
LENGTH_RANGE = (0.4, 2.5)

TURNS_PROMPT = (
    "Translate each numbered turn of this recorded conversation from {language} into natural English, "
    "faithfully and in full: every sentence, hesitation and repetition the speaker said, nothing added, "
    "nothing summarised, no explanations. Keep first and second person as spoken. A bracketed note "
    "marks words the transcriber was unsure of, such as [niezrozumiałe: words heard]: keep the brackets and "
    "translate both the note and every word inside it, as [unclear: words heard], never dropping them. "
    "The speakers are given for context only. "
    "Reply with JSON: {{\"turns\": [{{\"n\": <number>, \"text\": \"<English>\"}}, ...]}}, one item for every "
    "numbered turn.")
TEXT_PROMPT = (
    "Translate this personal journal writing from {language} into natural English, faithfully and in full: "
    "every sentence, nothing added, nothing summarised, no explanations. Keep the paragraphs and first person "
    "as written. Reply with the translation only.")

_LANGUAGES = {"pl": "Polish", "de": "German", "es": "Spanish", "fr": "French", "it": "Italian", "uk": "Ukrainian"}


class TranslationFailed(Exception):
    pass


def source_hash(content: str | None) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def language_of(content: str | None, content_format: str | None) -> str:
    """The record's language: a session says it, other writing is guessed."""
    from .sessions import guess_language, read

    if content_format == "session":
        session = read(content)
        if session is not None and session.language:
            return session.language
    return guess_language(content or "")


def needed(content: str | None, content_format: str | None) -> bool:
    return bool((content or "").strip()) and language_of(content, content_format) != "en"


def current(content: str | None, translation: str | None, translation_hash: str | None) -> str | None:
    """The stored translation, only while it is still of these words."""
    return translation if translation and translation_hash == source_hash(content) else None


def for_reading(content: str | None, translation: str | None, translation_hash: str | None) -> str | None:
    """What every reader uses: the English when there is a current one, else the original."""
    return current(content, translation, translation_hash) or content


def _system(prompt: str, language: str) -> str:
    from .session_vocabulary import gloss_line

    return " ".join(filter(None, (prompt.format(language=_LANGUAGES.get(language, language)), gloss_line())))


def _model():
    from .intelligence import Intelligence

    return Intelligence(model=settings.OPENAI_WORKER_MODEL, service_tier=settings.OPENAI_WORKER_SERVICE_TIER or None)


def _plausible(original: str, english: str) -> bool:
    if len(original) < 40:
        return bool(english.strip())
    return LENGTH_RANGE[0] <= len(english) / len(original) <= LENGTH_RANGE[1]


def _turns(texts: list[str], speakers: list[str], language: str, model: Any) -> list[str]:
    from .session_cleanup import _strip_fence

    system = _system(TURNS_PROMPT, language)
    out: list[str] = []
    for first in range(0, len(texts), TURNS_PER_CALL):
        batch = texts[first:first + TURNS_PER_CALL]
        request = "\n\n".join(f"[{first + k}] {speakers[first + k]}: {text}" for k, text in enumerate(batch))
        got: dict[int, str] = {}
        for _attempt in range(2):
            try:
                reply = model.chat(messages=[{"role": "user", "content": request}], system_prompt=system,
                                   temperature=None, max_tokens=16000, response_format={"type": "json_object"})
                got = {int(t["n"]): str(t.get("text") or "").strip()
                       for t in json.loads(_strip_fence(reply)).get("turns", []) if isinstance(t, dict)}
            except Exception as exc:
                logger.warning(f"Translation of turns {first}+ failed ({type(exc).__name__})")
                got = {}
            if all(_plausible(text, got.get(first + k, "")) for k, text in enumerate(batch)):
                break
        else:
            raise TranslationFailed(f"turns {first}-{first + len(batch) - 1} did not come back whole")
        out += [got[first + k] for k in range(len(batch))]
    return out


def _text(content: str, language: str, model: Any) -> str:
    system = _system(TEXT_PROMPT, language)
    pieces, piece = [], ""
    for paragraph in content.split("\n\n"):
        if piece and len(piece) + len(paragraph) > CHARS_PER_CALL:
            pieces.append(piece)
            piece = ""
        piece = f"{piece}\n\n{paragraph}" if piece else paragraph
    pieces.append(piece)
    out = []
    for original in pieces:
        english = ""
        for _attempt in range(2):
            try:
                english = model.chat(messages=[{"role": "user", "content": original}], system_prompt=system,
                                     temperature=None, max_tokens=16000).strip()
            except Exception as exc:
                logger.warning(f"Translation failed ({type(exc).__name__})")
                english = ""
            if _plausible(original, english):
                break
        else:
            raise TranslationFailed("the text did not come back whole")
        out.append(english)
    return "\n\n".join(out)


def translate(content: str, content_format: str | None, model: Any = None) -> str:
    """The English version of the record. Raises TranslationFailed rather than keep half of one."""
    from . import sessions

    model = model or _model()
    language = language_of(content, content_format)
    session = sessions.read(content) if content_format == "session" else None
    if session is None:
        return _text(content, language, model)
    roles = {"owner": "the owner", "therapist": "the therapist", "asker": "the question", "unclear": "unclear"}
    english = _turns([t.text for t in session.turns], [f"{t.label} ({roles[t.role]})" for t in session.turns],
                     language, model)
    close = content.find("\n---\n", 3) + len("\n---\n")
    head = content[:close].replace(f"\nlanguage: {session.language}\n", "\nlanguage: en\n", 1)
    body = [f"**[{sessions.clock(t.at)}] {t.label}:**\n{text}" for t, text in zip(session.turns, english)]
    return head + "\n" + "\n\n".join(body) + "\n"


def ensure(reflection_id: int, content: str | None, content_format: str | None,
           stored: str | None = None, stored_hash: str | None = None, model: Any = None) -> str | None:
    """The record's current English version, made and kept now if it has none.

    None when the record is English already, or when the translation failed:
    either way it is read in its own words, as before.
    """
    if not needed(content, content_format):
        return None
    if (kept := current(content, stored, stored_hash)) is not None:
        return kept
    try:
        english = translate(content or "", content_format, model)
    except Exception as exc:  # no provider, or not whole: read in its own words
        logger.warning(f"Record {reflection_id} not translated: {type(exc).__name__}: {exc}")
        return None
    with db.connection() as conn, conn.cursor() as cur:
        # Kept only if the words are still the ones translated: an edit in the
        # meantime makes this translation of nothing.
        cur.execute("""UPDATE reflections SET translation = %s, translation_hash = %s
                        WHERE id = %s AND content = %s""",
                    (english, source_hash(content), reflection_id, content))
        kept_now = cur.rowcount
        conn.commit()
    if not kept_now:
        return None
    logger.info(f"Record {reflection_id} translated into English")
    return english
