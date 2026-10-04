"""Owner-scoped, generation-checked storage for source-first personal dynamics.

A completed source read is neutral to the library. Drafts depend on every eligible
source; all three dated interpretations publish together, or not at all. Provider
calls run outside transactions under a per-owner session advisory lock.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from math import ceil

from psycopg2.extras import Json

from . import discovery_memo
from .config import settings
from .connections import (DISCOVERY_VERSION, MAX_DEFINITIONS, MAX_NEW_DEFINITIONS, MAX_PAIRS_PER_REPLY,
                          MAX_ROWS_PER_REPLY, discover_dynamics,
                          interpret_view)
from .database import db
from .dynamics import (
    DiscoveryDraft,
    DiscoveryView,
    Feedback,
    PersonalInsight,
    PersonalPattern,
    canonical_hash,
    claim_hash,
    definition_key,
    dynamic_id,
    project_range,
    snapshot_hash,
)
from .episodes import EXTRACTION_VERSION, Episode, ReadUnavailable
from .intelligence import Intelligence
from .interpretation_version import INTERPRETATION_VERSION
from .lens_matching import _MAX_ROWS as MAX_LENS_ROWS
from .library import library_hash, load
from .reading_version import VERIFIED_READER_VERSION as READER_VERSION
from .reference_evaluation import account_fingerprint

RANGES = ("all", "30d", "90d")


def period_bounds(period: str, today: date | None = None) -> tuple[date | None, date]:
    as_of = today if today is not None else datetime.now().astimezone().date()
    if period == "all":
        return None, as_of
    if period == "30d":
        return as_of - timedelta(days=29), as_of
    if period == "90d":
        return as_of - timedelta(days=89), as_of
    raise ValueError("Unknown writing range.")


def _state(cur, user_id: int, *, lock: str = "SHARE") -> tuple[int, int, str, str | None]:
    cur.execute("INSERT INTO discovery_state (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (user_id,))
    cur.execute(f"SELECT source_generation, review_generation, stage, error_kind "
                f"FROM discovery_state WHERE user_id = %s FOR {lock}", (user_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError("No such owner")
    return row


def _source_rows(cur, user_id: int, source_revisions: dict[int, int]) -> dict[int, dict]:
    """Reflection locks precede the state and account rows during read publication."""
    if (not isinstance(source_revisions, dict) or
            any(type(k) is not int or type(v) is not int or k <= 0 or v <= 0
                for k, v in source_revisions.items())):
        raise ValueError("invalid source revisions")
    sources = {}
    for source_id in sorted(source_revisions):
        cur.execute("""SELECT user_id, reflection_date, content, evidence_eligible,
                              discovery_revision FROM reflections WHERE id = %s FOR UPDATE""",
                    (source_id,))
        row = cur.fetchone()
        if (row is None or row[0] != user_id or not row[3] or
                not (row[2] or "").strip() or row[4] != source_revisions[source_id]):
            raise ValueError("Reading source is missing, ineligible, or changed")
        sources[source_id] = {"date": row[1], "content": row[2]}
    return sources


def _complete(cur, user_id: int) -> tuple[dict, dict[str, dict], int, int] | None:
    """All eligible source revisions, completed reads and account IDs form a manifest.

    A missing or outdated read is not an empty archive; return None. No source row
    locks are acquired here, so synthesis never inverts the writer lock order.
    """
    cur.execute("""SELECT r.id, r.discovery_revision, r.reflection_date,
                          d.source_revision, d.extraction_version, d.reader_version,
                          d.omitted_accounts, d.omitted_fields
                     FROM reflections r LEFT JOIN discovery_reads d ON d.reflection_id = r.id
                    WHERE r.user_id = %s AND r.evidence_eligible
                      AND r.content IS NOT NULL AND length(btrim(r.content)) > 0
                    ORDER BY r.id""", (user_id,))
    sources = cur.fetchall()
    if any(source_revision != revision or version != EXTRACTION_VERSION or
           reader != READER_VERSION for _, revision, _, source_revision, version,
           reader, _, _ in sources):
        return None
    cur.execute("""SELECT a.id, a.reflection_id, a.source_revision, a.reader_version, a.data
                     FROM discovery_accounts a
                    WHERE a.user_id = %s AND a.is_current ORDER BY a.reflection_id, a.id""",
                (user_id,))
    account_rows = cur.fetchall()
    source_index = {row[0]: row for row in sources}
    by_source: dict[int, list[str]] = {sid: [] for sid in source_index}
    accounts: dict[str, dict] = {}
    for aid, source_id, revision, reader, raw in account_rows:
        expected = source_index.get(source_id)
        if expected is None or expected[1] != revision or reader != READER_VERSION or raw is None:
            raise ValueError("current account does not belong to a completed source")
        episode = Episode.from_dict(raw)
        if (account_fingerprint(raw) != aid or len(episode.citations) != 1 or
                episode.citations[0].entry_id != source_id or
                episode.recorded_on != expected[2]):
            raise ValueError("current account does not match its source")
        by_source[source_id].append(aid)
        if aid in accounts:
            raise ValueError("duplicate current account")
        accounts[aid] = raw
    manifest = {"sources": [{"id": sid, "revision": revision,
                             "recordedOn": recorded.isoformat() if recorded else None,
                             "readerVersion": reader, "accountIds": by_source[sid]}
                            for sid, revision, recorded, _, _, reader, _, _ in sources]}
    return manifest, accounts, sum(row[6] for row in sources), sum(row[7] for row in sources)


def queue_synthesis_if_ready(cur, user_id: int) -> bool:
    """Enqueue at most once when the fully read archive needs synthesis/replay."""
    try:
        complete = _complete(cur, user_id)
    except ValueError:
        # A damaged older read cannot prevent a person from saving or deleting
        # new writing; its source must be repaired before synthesis is possible.
        return False
    if complete is None:
        return False
    manifest, _, _, _ = complete
    source_generation, review_generation, _, _ = _state(cur, user_id)
    digest = canonical_hash(manifest)
    model = settings.OPENAI_WORKER_MODEL
    try:
        lens_digest = library_hash(load())
    except (ValueError, OSError):
        # A broken optional interpretation library must fail its queue job, not
        # roll back a journal transaction that has already changed the source.
        lens_digest = ""
    cur.execute("""SELECT
                       (SELECT count(*) FROM discovery_views
                         WHERE user_id = %s AND source_generation = %s
                           AND review_generation = %s AND manifest_hash = %s
                           AND interpretation_version = %s AND library_hash = %s
                           AND model = %s AND as_of = %s),
                       EXISTS (SELECT 1 FROM discovery_drafts
                                WHERE user_id = %s AND source_generation = %s
                                  AND manifest_hash = %s AND discovery_version = %s
                                  AND model = %s)""",
                (user_id, source_generation, review_generation, digest,
                 INTERPRETATION_VERSION, lens_digest, model, period_bounds("all")[1],
                 user_id, source_generation, digest, DISCOVERY_VERSION, model))
    views_current, draft_current = cur.fetchone()
    if views_current == 3 and draft_current:
        return False
    cur.execute("""INSERT INTO processing_queue
                   (user_id, source_type, source_id)
                   VALUES (%s, 'personal_dynamics', %s)
                   ON CONFLICT (source_type, source_id) DO NOTHING RETURNING id""",
                (user_id, user_id))
    return cur.fetchone() is not None


def _store_reading(cur, user_id: int, episodes: list[dict], *,
                   source_revisions: dict[int, int], omitted_accounts: int = 0,
                   omitted_fields: int = 0, locked_sources: dict[int, dict] | None = None) -> None:
    """Validate every original citation before replacing this source's accounts."""
    if (len(source_revisions) != 1 or type(omitted_accounts) is not int or
            type(omitted_fields) is not int or min(omitted_accounts, omitted_fields) < 0):
        raise ValueError("reading metadata is invalid")
    sources = locked_sources if locked_sources is not None else _source_rows(cur, user_id, source_revisions)
    validated: dict[str, tuple[dict, int]] = {}
    for raw in episodes:
        episode = Episode.from_dict(raw)
        if len(episode.citations) != 1:
            raise ValueError("one reading account belongs to one reflection")
        cite = episode.citations[0]
        source = sources.get(cite.entry_id)
        if (source is None or cite.source_type != "reflection" or
                cite.entry_date != source["date"] or episode.recorded_on != source["date"] or
                not cite.text.strip() or cite.text not in source["content"]):
            raise ValueError("reading account lost its original source")
        aid = account_fingerprint(raw)
        if aid in validated:
            raise ValueError("duplicate account in one reading")
        validated[aid] = raw, cite.entry_id
    _state(cur, user_id, lock="UPDATE")
    sid, revision = next(iter(source_revisions.items()))
    cur.execute("""UPDATE discovery_accounts SET is_current = FALSE, data = NULL
                    WHERE user_id = %s AND reflection_id = %s""", (user_id, sid))
    for aid, (raw, source_id) in validated.items():
        cur.execute("""INSERT INTO discovery_accounts
                       (user_id, id, reflection_id, source_revision, reader_version, data, is_current)
                       VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                       ON CONFLICT (user_id, id) DO UPDATE
                         SET source_revision = EXCLUDED.source_revision,
                             reader_version = EXCLUDED.reader_version,
                             data = EXCLUDED.data, is_current = TRUE""",
                    (user_id, aid, source_id, revision, READER_VERSION, Json(raw)))
    cur.execute("""INSERT INTO discovery_reads
                   (reflection_id, source_revision, extraction_version, reader_version,
                    completed_at, omitted_accounts, omitted_fields)
                   VALUES (%s, %s, %s, %s, NOW(), %s, %s)
                   ON CONFLICT (reflection_id) DO UPDATE
                     SET source_revision = EXCLUDED.source_revision,
                         extraction_version = EXCLUDED.extraction_version,
                         reader_version = EXCLUDED.reader_version,
                         completed_at = EXCLUDED.completed_at,
                         omitted_accounts = EXCLUDED.omitted_accounts,
                         omitted_fields = EXCLUDED.omitted_fields""",
                (sid, revision, EXTRACTION_VERSION, READER_VERSION,
                 omitted_accounts, omitted_fields))
    queue_synthesis_if_ready(cur, user_id)
    cur.execute("""UPDATE discovery_state SET stage = 'discovering',
                  error_kind = NULL, updated_at = NOW()
                  WHERE user_id = %s AND EXISTS
                    (SELECT 1 FROM processing_queue
                      WHERE user_id = %s AND source_type = 'personal_dynamics'
                        AND source_id = %s)""", (user_id, user_id, user_id))


def _finalize(view: DiscoveryView, draft: DiscoveryDraft, manifest: dict,
              source_generation: int, review_generation: int, library_digest: str,
              model: str) -> DiscoveryView:
    source_binding = {"manifest": manifest, "identity": [p.as_dict() for p in draft.pair_decisions],
                      "discoveryVersion": DISCOVERY_VERSION}
    def bound(card: PersonalPattern | PersonalInsight):
        digest = claim_hash({"claims": card.as_dict(), "sourceBinding": source_binding})
        snapshot = snapshot_hash({"claimHash": digest, "sourceGeneration": source_generation,
                                  "reviewGeneration": review_generation,
                                  "manifestHash": canonical_hash(manifest),
                                  "interpretationVersion": INTERPRETATION_VERSION,
                                  "libraryHash": library_digest, "model": model,
                                  "range": view.range, "asOf": view.as_of,
                                  "lensMatches": ([row.as_dict() for row in card.lens_matches]
                                                  if isinstance(card, PersonalPattern) else None),
                                  "feedback": None})
        return card.model_copy(update={"claim_hash": digest, "snapshot": snapshot})
    return view.model_copy(update={"patterns": [bound(p) for p in view.patterns],
                                   "insights": [bound(i) for i in view.insights]})


def _captured(user_id: int):
    with db.connection() as conn, conn.cursor() as cur:
        source_gen, review_gen, _, _ = _state(cur, user_id)
        complete = _complete(cur, user_id)
        if complete is None:
            conn.commit()
            return None
        manifest, accounts, _, _ = complete
        digest = canonical_hash(manifest)
        cur.execute("""SELECT source_generation, manifest_hash, discovery_version, model, payload
                         FROM discovery_drafts WHERE user_id = %s""", (user_id,))
        cached = cur.fetchone()
        cur.execute("""SELECT dynamic_id, account_id, verdict, note
                         FROM discovery_membership_feedback WHERE user_id = %s""", (user_id,))
        corrections = cur.fetchall()
        conn.commit()
    model = settings.OPENAI_WORKER_MODEL
    draft = (DiscoveryDraft.from_dict(cached[4]) if cached and
             cached[:4] == (source_gen, digest, DISCOVERY_VERSION, model) else None)
    # The last draft from the same discovery version and model seeds the next:
    # its definitions carry forward, so only unseen accounts need proposals.
    previous = (DiscoveryDraft.from_dict(cached[4]) if draft is None and cached and
                cached[2:4] == (DISCOVERY_VERSION, model) else None)
    return source_gen, review_gen, manifest, digest, accounts, draft, previous, corrections, model


def _set_stage(user_id: int, source_generation: int, review_generation: int,
               stage: str) -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE discovery_state SET stage = %s, error_kind = NULL,
                      updated_at = NOW() WHERE user_id = %s
                        AND source_generation = %s AND review_generation = %s""",
                    (stage, user_id, source_generation, review_generation))
        conn.commit()


def process_user(user_id: int) -> None:
    """Recompose the full archive then all three views, with no partial publish."""

    # The pool connection is reserved for the session lock, not for provider work.
    with db.connection() as lock_conn:
        with lock_conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(73104, %s)", (user_id,))
            acquired = cur.fetchone()[0]
        lock_conn.commit()
        if not acquired:
            raise ReadUnavailable("synthesis_busy")
        try:
            captured = _captured(user_id)
            if captured is None:
                return
            (source_gen, review_gen, manifest, digest, accounts, cached, previous,
             feedback, model_name) = captured
            _set_stage(user_id, source_gen, review_gen,
                       "interpreting" if cached is not None else "discovering")
            episodes = [Episode.from_dict(raw) for raw in accounts.values()]
            usable = any(e.actor == "self" and e.record_kind in {"event", "self_report"}
                         for e in episodes)
            intelligence = (Intelligence(model=model_name, service_tier=settings.OPENAI_WORKER_SERVICE_TIER or None)
                            if usable and accounts else None)
            # Verdicts already paid for are reused; a failed run forgets its new replies.
            with discovery_memo.remembering(user_id):
                if cached is None:
                    proposed = discover_dynamics(episodes, intelligence, previous=previous)
                    draft = DiscoveryDraft.from_dict({**proposed.as_dict(), "userId": user_id})
                else:
                    draft = cached
                _set_stage(user_id, source_gen, review_gen, "interpreting")
                id_to_key = {dynamic_id(user_id, d): definition_key(d) for d in draft.definitions}
                corrections = {(id_to_key[dynamic_id_value], aid): verdict
                               for dynamic_id_value, aid, verdict, _ in feedback
                               if dynamic_id_value in id_to_key and aid in accounts}
                notes = {(id_to_key[dynamic_id_value], aid): note
                         for dynamic_id_value, aid, _, note in feedback
                         if dynamic_id_value in id_to_key and aid in accounts}
                lenses = load()
                lens_digest = library_hash(lenses)
                views = [
                    _finalize(interpret_view(draft, period, period_bounds(period)[1], lenses,
                                             intelligence, corrections=corrections,
                                             correction_notes=notes),
                              draft, manifest, source_gen, review_gen, lens_digest, model_name)
                    for period in RANGES]
                with db.connection() as conn, conn.cursor() as cur:
                    current_gen, current_review, _, _ = _state(cur, user_id, lock="UPDATE")
                    complete = _complete(cur, user_id)
                    if (complete is None or current_gen != source_gen or
                            current_review != review_gen or canonical_hash(complete[0]) != digest or
                            library_hash(load()) != lens_digest or
                            model_name != settings.OPENAI_WORKER_MODEL or
                            any(period_bounds(v.range)[1] != v.as_of for v in views)):
                        conn.commit()
                        return
                    if cached is None:
                        cur.execute("""INSERT INTO discovery_drafts
                                       (user_id, source_generation, manifest_hash, source_manifest,
                                        discovery_version, model, payload, completed_at)
                                       VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                                       ON CONFLICT (user_id) DO UPDATE SET
                                         source_generation = EXCLUDED.source_generation,
                                         manifest_hash = EXCLUDED.manifest_hash,
                                         source_manifest = EXCLUDED.source_manifest,
                                         discovery_version = EXCLUDED.discovery_version,
                                         model = EXCLUDED.model, payload = EXCLUDED.payload,
                                         completed_at = EXCLUDED.completed_at""",
                                    (user_id, source_gen, digest, Json(manifest),
                                     DISCOVERY_VERSION, model_name, Json(draft.as_dict())))
                    for view in views:
                        cur.execute("""INSERT INTO discovery_views
                                       (user_id, range, source_generation, review_generation,
                                        manifest_hash, as_of, interpretation_version, library_hash,
                                        model, payload, completed_at)
                                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                                       ON CONFLICT (user_id, range) DO UPDATE SET
                                         source_generation = EXCLUDED.source_generation,
                                         review_generation = EXCLUDED.review_generation,
                                         manifest_hash = EXCLUDED.manifest_hash,
                                         as_of = EXCLUDED.as_of,
                                         interpretation_version = EXCLUDED.interpretation_version,
                                         library_hash = EXCLUDED.library_hash,
                                         model = EXCLUDED.model,
                                         payload = EXCLUDED.payload,
                                         completed_at = EXCLUDED.completed_at""",
                                    (user_id, view.range, source_gen, review_gen, digest,
                                     view.as_of, INTERPRETATION_VERSION, lens_digest, model_name,
                                     Json(view.as_dict())))
                    cur.execute("""UPDATE discovery_state SET stage = 'ready', error_kind = NULL,
                                  updated_at = NOW() WHERE user_id = %s""", (user_id,))
                    conn.commit()
            discovery_memo.prune(user_id)
        finally:
            with lock_conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(73104, %s)", (user_id,))
                if not cur.fetchone()[0]:
                    raise RuntimeError("personal synthesis advisory lock was lost")
            lock_conn.commit()


def ensure_pending() -> None:
    """On startup/poll, repair missing current reads or dated/versioned views.

    Existing queued and exhausted work stays put; automatic polling never resets
    backoff or increments a lease's generation.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT r.id, r.user_id
                         FROM reflections r
                         LEFT JOIN discovery_reads d ON d.reflection_id = r.id
                         LEFT JOIN processing_queue q
                           ON q.source_type = 'discovery' AND q.source_id = r.id
                        WHERE r.evidence_eligible
                          AND r.content IS NOT NULL AND length(btrim(r.content)) > 0
                          AND q.id IS NULL
                          AND (d.reflection_id IS NULL OR
                               d.source_revision <> r.discovery_revision OR
                               d.extraction_version <> %s OR d.reader_version <> %s)
                        ORDER BY r.id FOR UPDATE OF r SKIP LOCKED LIMIT 200""",
                    (EXTRACTION_VERSION, READER_VERSION))
        queued = cur.fetchall()
        for source_id, user_id in queued:
            cur.execute("""INSERT INTO processing_queue (user_id, source_type, source_id)
                           VALUES (%s, 'discovery', %s)
                           ON CONFLICT (source_type, source_id) DO NOTHING""",
                        (user_id, source_id))
        cur.execute("SELECT id FROM users ORDER BY id")
        for (user_id,) in cur.fetchall():
            queue_synthesis_if_ready(cur, user_id)
        conn.commit()


class EvidenceNotReady(ValueError):
    """The owner's selected range has no current, fully checked generation."""


class EvidenceNotFound(ValueError):
    """No current, owner-scoped object has the requested ID."""


class EvidenceChanged(ValueError):
    """The client must review the present claims before changing a saved opinion."""

    def __init__(self):
        super().__init__("The selected evidence changed. Review it before sending.")


def _view(cur, user_id: int, period: str):
    if period not in RANGES:
        raise ValueError("unknown range")
    source_gen, review_gen, _, _ = _state(cur, user_id)
    complete = _complete(cur, user_id)
    if complete is None:
        return None
    manifest, accounts, omitted_accounts, omitted_fields = complete
    digest = canonical_hash(manifest)
    cur.execute("""SELECT source_generation, manifest_hash, discovery_version, model
                     FROM discovery_drafts WHERE user_id = %s""", (user_id,))
    current_draft = cur.fetchone()
    if current_draft != (source_gen, digest, DISCOVERY_VERSION, settings.OPENAI_WORKER_MODEL):
        return None
    cur.execute("""SELECT source_generation, review_generation, manifest_hash, as_of,
                          interpretation_version, library_hash, model, payload
                     FROM discovery_views WHERE user_id = %s AND range = %s""",
                (user_id, period))
    row = cur.fetchone()
    if row is None or row[:7] != (source_gen, review_gen, digest, period_bounds(period)[1],
                                  INTERPRETATION_VERSION, library_hash(load()),
                                  settings.OPENAI_WORKER_MODEL):
        return None
    view = DiscoveryView.from_dict(row[7])
    if view.range != period or view.as_of != row[3]:
        raise ValueError("stored view differs from its current metadata")
    return view, manifest, accounts, omitted_accounts, omitted_fields


def _feedback(cur, user_id: int, period: str, view: DiscoveryView) -> DiscoveryView:
    cur.execute("""SELECT object_kind, object_id, judged_hash, verdict, note, updated_at
                     FROM discovery_feedback WHERE user_id = %s AND range = %s""",
                (user_id, period))
    saved = {(kind, object_id): (judged, verdict, note, updated)
             for kind, object_id, judged, verdict, note, updated in cur.fetchall()}

    def apply(card, kind: str):
        row = saved.get((kind, card.id))
        if row is None:
            return card
        judged, verdict, note, updated = row
        feedback = Feedback(verdict=verdict, note=note, updated_at=updated.isoformat(),
                            needs_review=judged != card.claim_hash)
        return card.model_copy(update={
            "feedback": feedback,
            "snapshot": snapshot_hash({"base": card.snapshot, "feedback": feedback.as_dict()})})

    return view.model_copy(update={
        "patterns": [apply(p, "dynamic") for p in view.patterns],
        "insights": [apply(i, "insight") for i in view.insights]})


def _coverage(period: str, as_of: date, accounts: dict[str, dict]) -> dict:
    lower, _ = period_bounds(period, as_of)
    selected = [Episode.from_dict(raw) for raw in accounts.values()
                if lower is None or (raw["recordedOn"] is not None and
                                     lower <= date.fromisoformat(raw["recordedOn"]) <= as_of)]
    days = [ep.recorded_on for ep in selected if ep.recorded_on is not None]
    return {"range": period, "asOf": as_of.isoformat(),
            "recordedFrom": min(days).isoformat() if days else None,
            "recordedTo": max(days).isoformat() if days else None,
            "entryCount": len({c.entry_id for ep in selected for c in ep.citations}),
            "accountCount": len(selected),
            "undatedAccountCount": sum(ep.recorded_on is None for ep in selected)}


def _list(user_id: int, period: str) -> tuple[DiscoveryView | None, dict | None]:
    with db.connection() as conn, conn.cursor() as cur:
        loaded = _view(cur, user_id, period)
        if loaded is None:
            conn.commit()
            return None, None
        view, _, accounts, _, _ = loaded
        result = _feedback(cur, user_id, period, view)
        coverage = _coverage(period, view.as_of, accounts)
        conn.commit()
        return result, coverage


def patterns(user_id: int, period: str = "all") -> tuple[list[PersonalPattern], dict | None]:
    view, coverage = _list(user_id, period)
    return (view.patterns if view else []), coverage


def insights(user_id: int, period: str = "all") -> tuple[list[PersonalInsight], dict | None]:
    view, coverage = _list(user_id, period)
    return (view.insights if view else []), coverage


def overview(user_id: int, period: str = "all", *, kind: str = "dynamic") -> dict:
    """One generation for an entire range, its coverage, status and list token."""
    if kind not in {"dynamic", "insight"}:
        raise ValueError("unknown writing kind")
    key = "patterns" if kind == "dynamic" else "insights"
    with db.connection() as conn, conn.cursor() as cur:
        source_gen, review_gen, _, _ = _state(cur, user_id)
        loaded = _view(cur, user_id, period)
        if loaded is None:
            coverage = _coverage(period, period_bounds(period)[1], {})
            cards = []
        else:
            view, _, accounts, _, _ = loaded
            current = _feedback(cur, user_id, period, view)
            coverage = _coverage(period, view.as_of, accounts)
            cards = current.patterns if kind == "dynamic" else current.insights
        status = _inventory(cur, user_id)
        result = {key: [card.as_dict() for card in cards], "coverage": coverage,
                  "status": status,
                  "snapshot": snapshot_hash({
                      "range": period, "kind": kind, "sourceGeneration": source_gen,
                      "reviewGeneration": review_gen, "coverage": coverage,
                      "cards": [card.snapshot for card in cards]})}
        conn.commit()
        return result


def _detail(cur, user_id: int, period: str, kind: str, object_id: str):
    loaded = _view(cur, user_id, period)
    if loaded is None:
        raise EvidenceNotReady("The selected writing is being checked.")
    raw_view, _, accounts, omitted_accounts, omitted_fields = loaded
    view = _feedback(cur, user_id, period, raw_view)
    cards = view.patterns if kind == "dynamic" else view.insights
    card = next((row for row in cards if row.id == object_id), None)
    if card is None:
        raise EvidenceNotFound("No such current personal dynamic or insight.")
    cur.execute("SELECT payload FROM discovery_drafts WHERE user_id = %s", (user_id,))
    draft = DiscoveryDraft.from_dict(cur.fetchone()[0])
    cur.execute("""SELECT dynamic_id, account_id, verdict, note
                     FROM discovery_membership_feedback WHERE user_id = %s""", (user_id,))
    saved = cur.fetchall()
    id_to_key = {dynamic_id(user_id, d): definition_key(d) for d in draft.definitions}
    corrections = {(id_to_key[did], aid): verdict for did, aid, verdict, _ in saved
                   if did in id_to_key and aid in draft.episodes}
    notes = {(id_to_key[did], aid): note for did, aid, _, note in saved
             if did in id_to_key and aid in draft.episodes}
    projected = project_range(draft, period, view.as_of, corrections, notes)
    selected = {id_to_key[did]: did for did in
                ([card.id] if kind == "dynamic" else card.dynamic_ids)}
    if len(selected) != (1 if kind == "dynamic" else len(card.dynamic_ids)):
        raise ValueError("stored card refers to a missing checked definition")
    members = {did: [row.model_copy(update={"dynamic_id": did}).as_dict()
                     for row in projected.memberships if row.dynamic_id == key]
               for key, did in selected.items()}
    groups = {did: [g.as_dict() for g in projected.groups[key]]
              for key, did in selected.items()}
    source_ids = {row["accountId"] for rows in members.values() for row in rows}
    account_payload = {aid: {"id": aid, **projected.episodes[aid]} for aid in sorted(source_ids)}
    coverage = _coverage(period, view.as_of, accounts)
    result = {"accounts": account_payload, "memberships": members, "groups": groups,
              "coverage": coverage}
    if kind == "dynamic":
        lenses = {lens.id: lens for lens in load()}
        result["lenses"] = [
            {"id": lenses[m.lens_id].id,
             "family": lenses[m.lens_id].family,
             "name": lenses[m.lens_id].name,
             "sequence": lenses[m.lens_id].sequence,
             "possibleFunction": lenses[m.lens_id].possible_function,
             "immediateReturn": lenses[m.lens_id].immediate_return,
             "possibleLaterCost": lenses[m.lens_id].possible_later_cost,
             "requires": list(lenses[m.lens_id].requires),
             "notWhen": lenses[m.lens_id].not_when,
             "alternative": lenses[m.lens_id].alternative,
             "question": lenses[m.lens_id].question,
             "sourceIds": list(lenses[m.lens_id].source_ids),
             "sources": [asdict(source) for source in lenses[m.lens_id].sources]}
            for m in card.lens_matches]
        result["checks"] = {
            "checked": len(members[card.id]),
            "unclear": sum(row["role"] == "unclear" for row in members[card.id]),
            "omittedAccounts": omitted_accounts, "omittedFields": omitted_fields,
            "exceptionSearchComplete": True}
    return card, result


def pattern(user_id: int, dynamic_id_value: str, period: str = "all") -> dict:
    with db.connection() as conn, conn.cursor() as cur:
        card, detail = _detail(cur, user_id, period, "dynamic", dynamic_id_value)
        status = _inventory(cur, user_id)
        conn.commit()
        return {"pattern": card.as_dict(), **detail, "status": status, "snapshot": card.snapshot}


def insight(user_id: int, insight_id_value: str, period: str = "all") -> dict:
    with db.connection() as conn, conn.cursor() as cur:
        card, detail = _detail(cur, user_id, period, "insight", insight_id_value)
        status = _inventory(cur, user_id)
        conn.commit()
        return {"insight": card.as_dict(), **detail, "status": status, "snapshot": card.snapshot}


def resolve_discussion(user_id: int, ref: str | dict, *,
                       require_snapshot: bool = False) -> dict:
    """Resolve typed, owner-scoped evidence again before saving a chat turn."""
    from .evidence_ref import DayRef, DynamicRef, EvidenceNotCurrent, InsightRef, parse_ref
    from .evidence_ref import EvidenceChanged as DiscussionChanged
    from .evidence_ref import EvidenceNotFound as DiscussionNotFound

    pointer = parse_ref(ref)
    try:
        if isinstance(pointer, DynamicRef):
            evidence = pattern(user_id, pointer.dynamicId, pointer.range)
            card = evidence["pattern"]
            title, question = card["title"], card["openQuestion"]
        elif isinstance(pointer, InsightRef):
            evidence = insight(user_id, pointer.insightId, pointer.range)
            card = evidence["insight"]
            title, question = card["title"], card["question"]
        elif isinstance(pointer, DayRef):
            from .day_differences import detail_for_user
            evidence = detail_for_user(user_id, pointer.outcome, pointer.split,
                                       period=pointer.range)
            if evidence is None:
                raise EvidenceNotCurrent("This day comparison is no longer current.")
            title = f"{pointer.outcome.replace('_', ' ')} by {pointer.split.replace('_', ' ')}"
            question = "What else differed between these measured days?"
        else:
            raise ValueError("invalid evidence kind")
    except EvidenceNotReady as exc:
        raise EvidenceNotCurrent("The selected writing is being checked.") from exc
    except EvidenceNotFound as exc:
        raise DiscussionNotFound(str(exc)) from exc
    actual = (evidence["difference"]["snapshot"] if isinstance(pointer, DayRef)
              else card["snapshot"])
    changed = pointer.snapshot != actual
    if changed and require_snapshot:
        raise DiscussionChanged()
    current_ref = pointer.model_copy(update={"snapshot": actual})
    return {"ref": current_ref, "title": title, "question": question,
            "evidence": evidence, "changed": changed}


def set_feedback(user_id: int, kind: str, object_id: str, period: str,
                 snapshot: str, verdict: str | None, note: str | None) -> dict:
    if kind not in {"dynamic", "insight"} or verdict not in {
            None, "rings_true", "does_not", "unsure"} or (
            note is not None and (not isinstance(note, str) or len(note) > 1000)):
        raise ValueError("invalid feedback")
    with db.connection() as conn, conn.cursor() as cur:
        _state(cur, user_id, lock="UPDATE")
        card, _ = _detail(cur, user_id, period, kind, object_id)
        if card.snapshot != snapshot:
            raise EvidenceChanged()
        cur.execute("""INSERT INTO discovery_feedback
                       (user_id, object_kind, object_id, range, judged_hash,
                        verdict, note, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (user_id, object_kind, object_id, range)
                       DO UPDATE SET judged_hash = EXCLUDED.judged_hash,
                                     verdict = EXCLUDED.verdict,
                                     note = EXCLUDED.note, updated_at = NOW()""",
                    (user_id, kind, object_id, period, card.claim_hash, verdict, note))
        card, _ = _detail(cur, user_id, period, kind, object_id)
        conn.commit()
        return {"feedback": card.feedback.as_dict(), "snapshot": card.snapshot}


def set_membership_feedback(user_id: int, dynamic_id_value: str, account_id: str,
                            period: str, snapshot: str, verdict: str | None,
                            note: str | None) -> None:
    if verdict not in {None, "yes", "no", "unsure"} or (
            note is not None and (not isinstance(note, str) or len(note) > 1000)):
        raise ValueError("invalid account feedback")
    with db.connection() as conn, conn.cursor() as cur:
        _state(cur, user_id, lock="UPDATE")
        card, detail = _detail(cur, user_id, period, "dynamic", dynamic_id_value)
        if card.snapshot != snapshot:
            raise EvidenceChanged()
        if account_id not in {row["accountId"] for row in detail["memberships"][dynamic_id_value]}:
            raise EvidenceNotFound("No such current account classification.")
        if verdict is None and note is None:
            cur.execute("""DELETE FROM discovery_membership_feedback
                            WHERE user_id = %s AND dynamic_id = %s AND account_id = %s""",
                        (user_id, dynamic_id_value, account_id))
        else:
            cur.execute("""INSERT INTO discovery_membership_feedback
                           (user_id, dynamic_id, account_id, verdict, note, updated_at)
                           VALUES (%s, %s, %s, %s, %s, NOW())
                           ON CONFLICT (user_id, dynamic_id, account_id)
                           DO UPDATE SET verdict = EXCLUDED.verdict, note = EXCLUDED.note,
                                         updated_at = NOW()""",
                        (user_id, dynamic_id_value, account_id, verdict, note))
        cur.execute("""UPDATE discovery_state SET review_generation = review_generation + 1,
                      stage = 'interpreting', updated_at = NOW() WHERE user_id = %s""",
                    (user_id,))
        cur.execute("DELETE FROM discovery_views WHERE user_id = %s", (user_id,))
        db._queue(cur, user_id, "personal_dynamics", user_id)
        conn.commit()


#: Tokens in and out per request, by synthesis step. Measured on gpt-6-luna
#: on 2 October 2026 for proposals; the others are generous allowances for
#: one account with its definitions, or a few accounts with their pairs.
STEP_TOKENS = {
    "propose": (17_000, 1_700),
    "merge": (900, 700),
    "specific": (2_500, 600),
    "membership": (1_500, 1_100),
    "identity": (3_500, 1_100),
    "interpret": (4_000, 1_500),
    "refine": (1_500, 1_100),
}


def synthesis_steps(*, accounts: int, events: int, eligible: int, known_accounts: int = 0,
                    known_events: int = 0, known_definitions: int = 0) -> dict[str, int]:
    """Requests per step for the next synthesis run: an upper bound.

    `accounts` is every account; `events` only the owner's grounded events, the
    only accounts compared in pairs; `eligible` the accounts read for
    proposals (events and self-reports). With a seed (the last draft's
    definitions and accounts) only what is new is asked: everything else is
    a remembered verdict.
    """
    seeded = known_definitions > 0
    unseen_accounts = max(0, accounts - known_accounts) if seeded else accounts
    unseen_events = max(0, events - known_events) if seeded else events
    unseen_eligible = (ceil(eligible * unseen_accounts / accounts) if accounts else 0)
    propose = ceil(unseen_eligible / 20) if unseen_eligible else 0
    proposals = 6 * propose  # at most six definitions per proposal request
    merge_pairs = proposals * (proposals - 1) // 2 + proposals * known_definitions
    # An update adds new definitions next to the known ones, never more than
    # MAX_NEW_DEFINITIONS; each is checked against every account, old or new.
    added = min(MAX_NEW_DEFINITIONS, proposals) if seeded else min(MAX_DEFINITIONS, proposals)
    definitions = known_definitions + added if seeded else added
    membership = (ceil(definitions / MAX_ROWS_PER_REPLY) * unseen_accounts +
                  ceil(added * (accounts - unseen_accounts) / MAX_ROWS_PER_REPLY))
    identity_pairs = (unseen_events * (unseen_events - 1) // 2 +
                      unseen_events * (events - unseen_events))
    return {
        "propose": propose,
        "merge": ceil(merge_pairs / MAX_PAIRS_PER_REPLY),
        "specific": added,
        "membership": membership,
        "identity": ceil(identity_pairs / MAX_ROWS_PER_REPLY),
        "interpret": (3 * min(2, definitions) * (2 + ceil(24 * min(accounts, 3) / MAX_LENS_ROWS))
                      if definitions else 0),
        # A new definition without enough support may be reworded once, and the
        # rewording is checked against the whole archive again.
        "refine": added * (1 + ceil(accounts / MAX_ROWS_PER_REPLY)),
    }


def update_estimate(user_id: int, new_accounts: int, new_events: int) -> tuple[int, int, int]:
    """Requests and tokens, at most, for the update one new entry sets off.

    Read before the entry is: the counts come from the last draft, plus the
    accounts the entry is expected to add.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT jsonb_array_length(payload->'definitions'),
                              (SELECT count(*) FROM jsonb_object_keys(payload->'episodes')),
                              (SELECT count(*) FROM jsonb_each(payload->'episodes') AS e(id, episode)
                                WHERE episode->>'actor' = 'self' AND episode->>'recordKind' = 'event'
                                  AND coalesce(episode->>'situation', '') <> ''
                                  AND coalesce(episode->>'response', '') <> '')
                         FROM discovery_drafts
                        WHERE user_id = %s AND discovery_version = %s AND model = %s""",
                    (user_id, DISCOVERY_VERSION, settings.OPENAI_WORKER_MODEL))
        seeded = cur.fetchone()
    definitions, accounts, events = (int(v or 0) for v in seeded) if seeded else (0, 0, 0)
    steps = synthesis_steps(accounts=accounts + new_accounts, events=events + new_events,
                            eligible=accounts + new_accounts, known_accounts=accounts,
                            known_events=events, known_definitions=definitions)
    return (sum(steps.values()), sum(n * STEP_TOKENS[step][0] for step, n in steps.items()),
            sum(n * STEP_TOKENS[step][1] for step, n in steps.items()))


def _inventory(cur, user_id: int) -> dict:
    """Status and bounded approximate work in the caller's evidence transaction."""
    from .work_queue import MAX_ATTEMPTS

    _, _, stored_stage, error_kind = _state(cur, user_id)
    cur.execute("""SELECT r.evidence_eligible, r.content,
                          (d.reflection_id IS NOT NULL
                           AND d.source_revision = r.discovery_revision
                           AND d.extraction_version = %s
                           AND d.reader_version = %s),
                          d.omitted_accounts, d.omitted_fields,
                          q.attempts, q.last_error
                     FROM reflections r
                     LEFT JOIN discovery_reads d ON d.reflection_id = r.id
                     LEFT JOIN processing_queue q
                       ON q.source_type = 'discovery' AND q.source_id = r.id
                    WHERE r.user_id = %s""",
                (EXTRACTION_VERSION, READER_VERSION, user_id))
    rows = cur.fetchall()
    selected = [r for r in rows if r[0] and (r[1] or "").strip()]
    current = [r for r in selected if r[2]]
    stale = [r for r in selected if not r[2]]
    unread = [r for r in stale if r[5] is None]
    pending = [r for r in stale if r[5] is not None and r[5] < MAX_ATTEMPTS]
    failed = [r for r in stale if r[5] is not None and r[5] >= MAX_ATTEMPTS]
    cur.execute("""SELECT attempts, last_error FROM processing_queue
                    WHERE user_id = %s AND source_type = 'personal_dynamics'
                      AND source_id = %s""", (user_id, user_id))
    synthesis_job = cur.fetchone()
    cur.execute("""SELECT completed_at FROM discovery_views
                    WHERE user_id = %s AND range = 'all'""", (user_id,))
    completion = cur.fetchone()
    ready = _view(cur, user_id, "all") is not None
    missing_chars = sum(len(r[1]) for r in stale)
    # Accounts already read are counted by kind: every account is checked
    # against every definition, only the owner's grounded events are compared
    # in pairs, and proposals are read from events and self-reports. Entries
    # not yet read are assumed to hold accounts like the ones that have been.
    cur.execute("""SELECT count(*),
                          count(*) FILTER (WHERE a.data->>'actor' = 'self'
                                           AND a.data->>'recordKind' = 'event'
                                           AND coalesce(a.data->>'situation', '') <> ''
                                           AND coalesce(a.data->>'response', '') <> ''),
                          count(*) FILTER (WHERE a.data->>'actor' = 'self'
                                           AND a.data->>'recordKind' IN ('event', 'self_report'))
                     FROM discovery_accounts a
                     JOIN discovery_reads d ON d.reflection_id = a.reflection_id
                     JOIN reflections r ON r.id = a.reflection_id AND r.user_id = a.user_id
                    WHERE a.user_id = %s AND a.is_current
                      AND r.evidence_eligible AND r.content IS NOT NULL
                      AND length(btrim(r.content)) > 0
                      AND a.source_revision = r.discovery_revision
                      AND a.reader_version = %s
                      AND d.source_revision = r.discovery_revision
                      AND d.extraction_version = %s AND d.reader_version = %s""",
                (user_id, READER_VERSION, EXTRACTION_VERSION, READER_VERSION))
    read_accounts, read_events, read_eligible = cur.fetchone()
    per_entry = (read_accounts / len(current)) if current else 1.0
    def scaled(count: int) -> int:
        return count + ceil(len(stale) * (count / len(current) if current else per_entry))
    accounts, events, eligible = scaled(read_accounts), scaled(read_events), scaled(read_eligible)
    reading_requests = 2 * len(stale)
    cur.execute("""SELECT jsonb_array_length(payload->'definitions'),
                          (SELECT count(*) FROM jsonb_object_keys(payload->'episodes')),
                          (SELECT count(*) FROM jsonb_each(payload->'episodes') AS e(id, episode)
                            WHERE episode->>'actor' = 'self' AND episode->>'recordKind' = 'event'
                              AND coalesce(episode->>'situation', '') <> ''
                              AND coalesce(episode->>'response', '') <> '')
                     FROM discovery_drafts
                    WHERE user_id = %s AND discovery_version = %s AND model = %s""",
                (user_id, DISCOVERY_VERSION, settings.OPENAI_WORKER_MODEL))
    seeded = cur.fetchone()
    known_definitions, known_accounts, known_events = (
        (int(seeded[0] or 0), int(seeded[1] or 0), int(seeded[2] or 0)) if seeded else (0, 0, 0))
    if ready or not accounts:
        synthesis_requests, synthesis_in, synthesis_out = 0, 0, 0
    else:
        steps = synthesis_steps(accounts=accounts, events=events, eligible=eligible,
                                known_accounts=known_accounts, known_events=known_events,
                                known_definitions=known_definitions)
        synthesis_requests = sum(steps.values())
        synthesis_in = sum(n * STEP_TOKENS[step][0] for step, n in steps.items())
        synthesis_out = sum(n * STEP_TOKENS[step][1] for step, n in steps.items())
    tokens_in = missing_chars // 4 * 2 + 1800 * reading_requests + synthesis_in
    tokens_out = reading_requests * 1100 + synthesis_out
    stage = ("failed" if failed or synthesis_job and synthesis_job[0] >= MAX_ATTEMPTS else
             "reading" if stale else
             "ready" if ready else
             stored_stage if synthesis_job else "interpreting")
    try:
        lens_version = library_hash(load())
    except (ValueError, OSError):
        lens_version = None
    return {
        "readerVersion": READER_VERSION, "discoveryVersion": DISCOVERY_VERSION,
        "interpretationVersion": INTERPRETATION_VERSION,
        "libraryVersion": lens_version, "model": settings.OPENAI_WORKER_MODEL,
        "stage": stage, "errorKind": error_kind,
        "eligibleEntries": len(selected), "currentEntries": len(current),
        "unreadEntries": len(unread), "pendingEntries": len(pending),
        "failedEntries": len(failed), "excludedEntries": len(rows) - len(selected),
        "omittedAccounts": sum(r[3] or 0 for r in current),
        "omittedFields": sum(r[4] or 0 for r in current),
        "synthesisPending": bool(synthesis_job and synthesis_job[0] < MAX_ATTEMPTS),
        "synthesisFailed": bool(synthesis_job and synthesis_job[0] >= MAX_ATTEMPTS),
        "lastCompletedAt": completion[0].isoformat() if completion else None,
        "estimate": {
            "readingRequests": reading_requests, "synthesisRequests": synthesis_requests,
            "tokensIn": tokens_in, "tokensOut": tokens_out,
            "costText": Intelligence.estimate(
                settings.OPENAI_WORKER_MODEL, tokens_in, tokens_out,
                service_tier=settings.OPENAI_WORKER_SERVICE_TIER or None),
            "approximate": True}}


def inventory(user_id: int) -> dict:
    """Currentness, failure and stage-aware approximate work; no provider call."""
    with db.connection() as conn, conn.cursor() as cur:
        result = _inventory(cur, user_id)
        conn.commit()
        return result


def refresh(user_id: int, scope: str) -> dict:
    """Idempotently queue only unread or exhausted work; never renew a lease."""
    if scope not in {"unread", "failed"}:
        raise ValueError("unknown refresh scope")
    from .work_queue import MAX_ATTEMPTS
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT r.id, r.discovery_revision, d.source_revision,
                              d.extraction_version, d.reader_version,
                              q.id, q.attempts
                         FROM reflections r
                         LEFT JOIN discovery_reads d ON d.reflection_id = r.id
                         LEFT JOIN processing_queue q
                           ON q.source_type = 'discovery' AND q.source_id = r.id
                        WHERE r.user_id = %s AND r.evidence_eligible
                          AND r.content IS NOT NULL AND length(btrim(r.content)) > 0
                        ORDER BY r.id FOR UPDATE OF r""", (user_id,))
        sources = cur.fetchall()
        queued = 0
        for sid, revision, read_revision, extraction, reader, job_id, attempts in sources:
            stale = (read_revision != revision or extraction != EXTRACTION_VERSION or
                     reader != READER_VERSION)
            if not stale or scope == "unread" and job_id is not None:
                continue
            if scope == "failed" and (job_id is None or attempts < MAX_ATTEMPTS):
                continue
            if job_id is None:
                cur.execute("""INSERT INTO processing_queue
                               (user_id, source_type, source_id) VALUES (%s, 'discovery', %s)
                               ON CONFLICT (source_type, source_id) DO NOTHING RETURNING id""",
                            (user_id, sid))
                queued += cur.fetchone() is not None
            else:
                db._queue(cur, user_id, "discovery", sid)
                queued += 1
        synthesis = False
        if not any(revision != read_revision or extraction != EXTRACTION_VERSION or
                   reader != READER_VERSION for _, revision, read_revision, extraction,
                   reader, _, _ in sources):
            if scope == "unread":
                synthesis = queue_synthesis_if_ready(cur, user_id)
            else:
                cur.execute("""SELECT attempts FROM processing_queue
                                WHERE source_type = 'personal_dynamics' AND source_id = %s
                                  AND user_id = %s FOR UPDATE""", (user_id, user_id))
                row = cur.fetchone()
                if row and row[0] >= MAX_ATTEMPTS:
                    db._queue(cur, user_id, "personal_dynamics", user_id)
                    synthesis = True
        conn.commit()
    return {"queuedEntries": queued, "queuedSynthesis": synthesis}
