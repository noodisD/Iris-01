"""Read one eligible journal entry, then publish only if its source is unchanged."""

from __future__ import annotations

from .config import settings
from .database import db
from .discovery import _source_rows, _store_reading
from .episodes import EXTRACTION_VERSION, EpisodeReader, ReadUnavailable, comparable
from .connections import label_many
from .intelligence import Intelligence
from .library import library_hash, load


def _completed(cur, reflection_id: int, revision: int, library_digest: str) -> bool:
    cur.execute(
        """SELECT 1 FROM discovery_reads
            WHERE reflection_id = %s AND source_revision = %s
              AND extraction_version = %s AND library_hash = %s""",
        (reflection_id, revision, EXTRACTION_VERSION, library_digest))
    return cur.fetchone() is not None


def process_reflection(reflection_id: int) -> None:
    """Extract and label outside a transaction; recheck under a source-row lock.

    A concurrent worker's identical completion wins. The queue's generation
    check independently ensures a source edit cannot retire its newer job.
    """
    patterns = load()
    digest = library_hash(patterns)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT user_id, reflection_date, content, content_format, discovery_revision
                 FROM reflections WHERE id = %s AND evidence_eligible
                   AND content IS NOT NULL AND length(trim(content)) > 0""",
            (reflection_id,))
        row = cur.fetchone()
        if row is None:
            return
        user_id, date, content, content_format, revision = row
        if _completed(cur, reflection_id, revision, digest):
            return
    entry = {"id": reflection_id, "date": date, "content": content,
             "content_format": content_format, "source_type": "reflection",
             "discovery_revision": revision}
    try:
        model = Intelligence(model=settings.OPENAI_WORKER_MODEL)
    except Exception:
        raise ReadUnavailable("Discovery provider unavailable") from None
    reader = EpisodeReader(user_id, intelligence=model)
    try:
        episodes = reader.read([entry])
    except ReadUnavailable as exc:
        # The provider's chained exception may echo source text. Keep only the
        # reader's sanitized failure category in queue logs and traces.
        raise ReadUnavailable(str(exc)) from None
    usable = comparable(episodes)
    matched = {}
    by = {}
    if usable:
        for start in range(0, len(patterns), 5):
            batch = patterns[start:start + 5]
            try:
                results, _ = label_many(
                    [(p.id, p.statement, p.markers) for p in batch], episodes, model)
            except ReadUnavailable as exc:
                raise ReadUnavailable(str(exc)) from None
            if set(results) != {p.id for p in batch}:
                raise ReadUnavailable("Discovery labels incomplete")
            for pattern in batch:
                matched[pattern.id] = results[pattern.id]
                by[pattern.id] = settings.OPENAI_WORKER_MODEL
    labels = {"accounts": len(usable), "extractionVersion": EXTRACTION_VERSION,
              "libraryHash": digest, "labels": matched, "by": by}
    with db.connection() as conn, conn.cursor() as cur:
        try:
            sources = _source_rows(cur, user_id, {reflection_id: revision})
        except ValueError:
            # The edit/delete won the row lock; never publish old words.
            return
        if library_hash(load()) != digest:
            raise ReadUnavailable("Discovery library changed during reading")
        if _completed(cur, reflection_id, revision, digest):
            return
        _store_reading(cur, user_id, [e.as_dict() for e in episodes], labels,
                       source_revisions={reflection_id: revision},
                       extraction_version=EXTRACTION_VERSION, library_hash=digest,
                       omitted_accounts=reader.omitted_accounts, locked_sources=sources)
        conn.commit()
