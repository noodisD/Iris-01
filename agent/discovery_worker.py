"""Read one eligible reflection without seeing or labelling the editorial library."""
from __future__ import annotations

from dataclasses import replace

from .config import settings
from .connections import check_account_fields
from .database import db
from .discovery import _source_rows, _store_reading
from .dynamics import validate_field_checks
from .episodes import EXTRACTION_VERSION, EpisodeReader, ReadUnavailable
from .intelligence import Intelligence
from .readable import ensure_copy
from .reading_version import VERIFIED_READER_VERSION as READER_VERSION


def _completed(cur, reflection_id: int, revision: int) -> bool:
    cur.execute("""SELECT 1 FROM discovery_reads
                    WHERE reflection_id = %s AND source_revision = %s
                      AND extraction_version = %s AND reader_version = %s""",
                (reflection_id, revision, EXTRACTION_VERSION, READER_VERSION))
    return cur.fetchone() is not None


def verify_reading(episodes, intelligence):
    """Use the production contextual gate for persisted and diagnostic reads."""
    kept = []
    dropped = 0
    omitted_fields = 0
    for episode in episodes:
        checked = check_account_fields(episode, intelligence)
        validate_field_checks(episode, checked)
        unsupported = {field.field for field in checked.checks
                       if field.verdict != "supported"}
        if ((episode.record_kind == "event" and
             bool(unsupported & {"situation", "response"})) or
                (episode.record_kind == "self_report" and "self_report" in unsupported)):
            dropped += 1
            continue
        omitted_fields += len(unsupported)
        kept.append(replace(episode, **dict.fromkeys(unsupported)))
    return kept, dropped, omitted_fields


def _unique(episodes):
    """One of each account. A reader that returns the same account twice, field
    for field, has said nothing new the second time; the store refuses a reading
    holding a duplicate, which threw away every other account in the entry."""
    from .reference_evaluation import account_fingerprint

    seen, unique = set(), []
    for episode in episodes:
        key = account_fingerprint(episode.as_dict())
        if key not in seen:
            seen.add(key)
            unique.append(episode)
    return unique


def process_reflection(reflection_id: int) -> None:
    """Publish only source-grounded fields for the still-current source revision.

    Provider extraction/checking happens without a row lock. The reflection then
    locks before owner state and account rows, in the same transaction that marks
    the read complete and queues full-archive synthesis when all reads are ready.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT user_id, reflection_date, content, content_format,
                              discovery_revision, reading_copy
                         FROM reflections WHERE id = %s AND evidence_eligible
                           AND content IS NOT NULL AND length(btrim(content)) > 0""",
                    (reflection_id,))
        row = cur.fetchone()
        if row is None:
            return
        user_id, recorded, content, content_format, revision, stored_copy = row
        if _completed(cur, reflection_id, revision):
            return
    entry = {"id": reflection_id, "date": recorded, "content": content,
             "content_format": content_format, "source_type": "reflection"}
    try:
        model = Intelligence(model=settings.OPENAI_WORKER_MODEL,
                             service_tier=settings.OPENAI_WORKER_SERVICE_TIER or None)
    except Exception:
        raise ReadUnavailable("no_provider") from None
    reader = EpisodeReader(user_id, intelligence=model)
    # Dictated in one breath, an entry is read from its reading copy: the same
    # words punctuated, so quotes still resolve to the entry's own text.
    copy = None if content_format == "session" else ensure_copy(reflection_id, content, stored_copy, model)
    try:
        episodes = reader.read([entry], readable={str(reflection_id): copy} if copy else None)
        kept, dropped, omitted = verify_reading(episodes, model)
        omitted += reader.omitted_fields
    except ReadUnavailable as exc:
        raise ReadUnavailable(str(exc)) from None
    except ValueError:
        raise ReadUnavailable("invalid_field_checks") from None
    kept = _unique(kept)
    with db.connection() as conn, conn.cursor() as cur:
        try:
            sources = _source_rows(cur, user_id, {reflection_id: revision})
        except ValueError:
            return  # The edit/deletion won the source lock.
        if _completed(cur, reflection_id, revision):
            return
        _store_reading(cur, user_id, [ep.as_dict() for ep in kept],
                       source_revisions={reflection_id: revision},
                       omitted_accounts=reader.omitted_accounts + dropped,
                       omitted_fields=omitted, locked_sources=sources)
        conn.commit()
