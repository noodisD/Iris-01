"""A pattern that was noticed by reading, then measured.

Every theme until now is a cluster of embeddings with a label written after the
fact. That can say how often an unnamed group of entries recurred and nothing
else, and on the owner's archive it split one subject into five near-identical
themes of two to seven occurrences each — none of which named a behaviour.

A construct comes the other way round. The reading engine
(`agent/observations.py`) notices something and proves it with quotes checked
verbatim against stored entries; the owner confirms it; and only then is it
measured. Because it is stored as a theme, every existing engine measures it
with no new arithmetic — trajectory, resolution, tension, leverage and decision
impact all iterate themes generically.

Three rules hold this together:

- **The centroid is built from the owner's sentences, never from the claim.**
  The model's wording describes the pattern; the quotes *are* the pattern
  (ADR-0014). Embedding the claim would anchor a construct in how a model talks.
- **A candidate is not measured.** It exists, it has prototypes, it can be
  reviewed — and `db.get_themes` does not return it, so no engine sees it until
  the owner says so.
- **Matching happens in the shared comparison space** (`agent/comparison.py`).
  Raw cosine against one person's writing matches nearly everything, which is
  how one theme once took 121 of 132 entries.
"""

from __future__ import annotations

import hashlib
import logging
import re

import numpy as np

from .comparison import ComparisonSpace
from .database import db
from .persistence import entry_snippet
from .timeutils import utc_now

logger = logging.getLogger(__name__)

#: A construct needs a name short enough to read on a card. The claim is kept
#: whole in `definition`; this is only what the engines print.
SUMMARY_MAX_CHARS = 72

#: What a construct's occurrences mean. These never share a count or a
#: confidence label: a tally of mentions that reads as a tally of actions is the
#: misunderstanding this distinction exists to prevent.
CLAIM_MENTION = "mention"      # the subject appears in the writing
CLAIM_BEHAVIOUR = "behaviour"  # the thing happened — not yet supportable


def proposal_key(observation) -> str:
    """A stable identity for a proposal, so a rerun recognises it.

    Reading unchanged writing produces the same findings again. Without an
    identity that survives between runs, a second read offers back a proposal
    the owner already rejected, and quietly creates a duplicate of one they
    already confirmed — asking them to decide something they have decided.

    Derived from the claim and the writing it rests on, not from a row id: two
    runs that found the same thing in the same sentences are the same proposal,
    whichever order the passes finished in.
    """
    claim = re.sub(r"[^a-z0-9 ]+", "", (getattr(observation, "claim", "") or "").lower()).strip()
    cited = sorted(
        f"{c.source_type}:{c.entry_id}:{c.text}"
        for c in (getattr(observation, "citations", ()) or ())
    )
    return hashlib.sha256("|".join([claim, *cited]).encode()).hexdigest()[:32]


def _summarise(claim: str) -> str:
    """A card-sized name for the pattern, cut at a word boundary."""
    text = " ".join((claim or "").split())
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    cut = text[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0]
    return (cut or text[:SUMMARY_MAX_CHARS]).rstrip(" ,.;:") + "…"


def promote(user_id: int, observation, run_id: int = None) -> int | None:
    """Store a discovered observation as a candidate construct.

    Returns the theme id, or None if the observation carried nothing that could
    anchor it. Nothing is measured as a result of this call.
    """
    citations = list(getattr(observation, "citations", ()) or ())
    if not citations:
        logger.warning("Refusing to promote an observation with no citations")
        return None

    # Imported here rather than at module scope: agent.pipeline imports this
    # module, so importing it back at load time makes the package uninstallable
    # — agent.work_queue imports pipeline, which imports constructs, which would
    # import a pipeline that has not finished defining anything yet.
    from .pipeline import generate_embedding

    vectors, prototypes = [], []
    for citation in citations:
        try:
            vector = generate_embedding(citation.text)
        except Exception as e:
            logger.error(f"Could not embed a citation, skipping it: {e}")
            continue
        vectors.append(np.asarray(vector, dtype=np.float64))
        prototypes.append((citation, vector))

    if not vectors:
        logger.warning("Refusing to promote: no citation could be embedded")
        return None

    centroid = np.mean(vectors, axis=0)
    # Recordings carry no date, by design (ADR-0013). The columns are NOT NULL,
    # so they still need a value — but a construct built only from undated
    # writing has no span, and stamping the moment of discovery made four
    # candidates read as though they were written that afternoon. The flag says
    # the stored value means nothing; the review surface reports no span at all.
    dates = [c.entry_date for c in citations if getattr(c, "entry_date", None)]
    undated = not dates
    first = min(dates).isoformat() if dates else utc_now().isoformat()
    last = max(dates).isoformat() if dates else utc_now().isoformat()

    theme_id = db.create_theme(
        user_id=user_id,
        centroid_embedding=centroid.tolist(),
        summary=_summarise(observation.claim),
        first_seen_at=first,
        last_seen_at=last,
        # Occurrences are written by scan(), after confirmation. Claiming a
        # count here would be asserting evidence nobody has measured yet.
        occurrence_count=0,
        origin="observed",
        definition=observation.claim,
        status="candidate",
        # A verified quote proves the subject appears in the writing, and
        # nothing stronger. Claiming the behaviour happened needs actor, event
        # identity, negation and retrospective reference — none of which is
        # checked yet, and two quotes explicitly denying a behaviour currently
        # pass verification. So nothing is born as a behaviour claim.
        claim_kind=CLAIM_MENTION,
        span_is_undated=undated,
    )

    for citation, vector in prototypes:
        db.add_theme_prototype(
            theme_id=theme_id,
            source_type=getattr(citation, "source_type", "reflection"),
            source_id=getattr(citation, "entry_id", None),
            quote=citation.text,
            vector=vector,
        )

    db.set_theme_proposal(theme_id, proposal_key(observation), run_id)
    logger.info(f"Promoted a candidate construct {theme_id} with {len(prototypes)} prototype(s)")
    return theme_id


def candidates(user_id: int) -> list[dict]:
    """Every construct awaiting the owner's decision, with its evidence.

    A candidate is only reviewable if the quotes come with it: the whole point
    of confirming is reading the sentences the claim rests on, not taking a
    model's word for the claim.
    """
    out = []
    for theme in db.get_themes_by_status(user_id, "candidate"):
        prototypes = db.get_theme_prototypes(theme["id"])
        out.append({
            "id": str(theme["id"]),
            "claim": theme["definition"] or theme["summary"],
            "summary": theme["summary"],
            "origin": theme["origin"],
            "claimKind": theme.get("claim_kind"),
            # No span rather than a placeholder presented as a date.
            "spanStart": None if theme.get("span_is_undated") else _iso(theme["first_seen_at"]),
            "spanEnd": None if theme.get("span_is_undated") else _iso(theme["last_seen_at"]),
            "quotes": [
                {
                    "text": p["quote"],
                    "entryId": str(p["source_id"]) if p["source_id"] is not None else None,
                    "sourceType": p["source_type"],
                    # A staged recording has no date, so it can be read and
                    # quoted but can never become an occurrence.
                    "citable": p["source_type"] == "reflection",
                }
                for p in prototypes
            ],
        })
    return out


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def discover(user_id: int, intelligence=None, include_staged: bool = True) -> list[dict]:
    """Read the whole archive and stage what it found for review.

    Nothing here is measured. Each observation that survives verification
    becomes a candidate the owner can confirm or reject; until they do, no
    engine sees any of it.
    """
    from .observations import ObservationEngine

    engine = ObservationEngine(user_id, intelligence=intelligence)
    observations, run_id = engine.read_archive(include_staged=include_staged)

    # A decision already made is not offered again. Rejecting a proposal has to
    # mean something the next run respects, or rejection is only a way of
    # clearing the screen until someone presses the button.
    already_decided = db.get_decided_proposal_keys(user_id)
    staged = skipped = 0
    for observation in observations:
        if proposal_key(observation) in already_decided:
            skipped += 1
            continue
        if promote(user_id, observation, run_id=run_id) is not None:
            staged += 1

    if run_id is not None:
        db.record_run_candidates(run_id, staged)
    logger.info(
        f"Discovery staged {staged} candidate(s) for user {user_id}, "
        f"{skipped} already decided")
    return candidates(user_id)


def reject(theme_id: int) -> bool:
    """The owner did not recognise this. It is kept, and never measured.

    Retracting an *active* construct has to take its evidence with it. Status
    alone is not a retraction: occurrences stay in the table, and the cached
    readers that join themes without checking status would go on feeding chat
    from a pattern the owner had just withdrawn.

    Returns False when there was nothing to reject.
    """
    theme = db.get_theme_by_id(theme_id)
    if not theme or theme.get("origin") != "observed" or theme.get("status") == "rejected":
        logger.info(f"Construct {theme_id} is not in a state that can be rejected")
        return False

    db.retract_construct(theme_id)
    logger.info(f"Construct {theme_id} rejected, and its evidence withdrawn")
    return True


def confirm(theme_id: int) -> int:
    """The owner vouched for this. Measure it, and publish both at once.

    Matching happens first and writes nothing. Only then are the status and the
    evidence committed together, so a failure while matching leaves the
    construct exactly where it was — a candidate, still on the review screen,
    rather than an active pattern with no evidence behind it.

    Returns the occurrences written, or -1 when the construct was not in a state
    that may be confirmed (already active, rejected, or not one the reader
    proposed).
    """
    theme = db.get_theme_by_id(theme_id)
    if theme and theme.get("claim_kind") == CLAIM_BEHAVIOUR:
        # Refused rather than measured. Verification checks that a quote appears
        # in an entry; it does not check that the entry records the event, so a
        # behaviour count would rest on a proof nobody has built.
        logger.warning(
            f"Construct {theme_id} claims a behaviour, which cannot yet be evidenced; refused")
        return -1

    memberships = _memberships(theme_id)
    if memberships is None:
        return -1
    written = db.publish_construct(theme_id, memberships)
    if written < 0:
        return -1
    logger.info(f"Construct {theme_id} confirmed, {written} occurrence(s) recorded")
    return written


def scan(theme_id: int) -> int:
    """Re-measure a construct that is already active, and record what it finds.

    Confirmation does not go through here: it computes memberships and publishes
    them with the status in one transaction (see `confirm`). This is the path for
    re-scanning something the owner has already agreed to.
    """
    memberships = _memberships(theme_id)
    if memberships is None:
        return 0
    for occ in memberships:
        db.add_theme_occurrence(
            theme_id=theme_id,
            source_type=occ["source_type"],
            source_id=occ["source_id"],
            snippet=occ["snippet"],
            similarity_score=occ["similarity_score"],
            occurred_at=occ["occurred_at"],
        )
    db.update_theme_stats(theme_id)
    return len(memberships)


def classify(user_id: int, source_type: str, source_id: int, embedding,
             content: str, occurred_at) -> list[int]:
    """Test one new entry against every construct the owner has confirmed.

    Clustering is exclusive — an entry joins the single closest cluster — because
    it answers "what is this entry mostly about". A construct answers a different
    question, "does this entry show X", and several can be true of one entry at
    once. Running constructs through the exclusive competition meant an entry
    could go to a cluster on ingestion and to a construct on replay, so
    confirming a construct changed its measured frequency for reasons that were
    routing rather than writing.

    Returns the construct ids this entry was added to.
    """
    actives = db.get_themes_by_origin(user_id, "observed")
    if not actives:
        return []

    space = ComparisonSpace(user_id)
    _, match_threshold, _ = space.space()
    entry = space.project(embedding)[0]

    matched = []
    for theme in actives:
        centroid = theme.get("centroid_embedding")
        if centroid is None:
            continue
        centroid_in_space = space.project(_as_vector(centroid), are_centroids=True)[0]
        similarity = float(centroid_in_space @ entry)
        if similarity < match_threshold:
            continue
        db.add_theme_occurrence(
            theme_id=theme["id"],
            source_type=source_type,
            source_id=source_id,
            # The entry's own words. `content` here is the embedded text, which
            # wraps a reflection in application metadata.
            snippet=entry_snippet(source_type, source_id, 500),
            similarity_score=similarity,
            # str(occurred_at) was the fallback here, which turned a missing
            # date into the literal string "None" on its way to a timestamp
            # column. An absent date is stored as absent.
            occurred_at=(occurred_at.isoformat()
                         if hasattr(occurred_at, "isoformat") else None),
            # The owner never saw this one: the detector proposed it.
            admission_basis="similarity",
        )
        db.update_theme_stats(theme["id"])
        matched.append(theme["id"])
        logger.info(f"{source_type} {source_id} matched construct {theme['id']} ({similarity:.3f})")
    return matched


def _memberships(theme_id: int) -> list | None:
    """Every entry this construct describes. Writes nothing.

    Returns None when the construct cannot be matched at all — no such row, no
    prototypes, no vectors — so a caller can tell "nothing matched" apart from
    "this could not be measured".
    """
    theme = db.get_theme_by_id(theme_id)
    if not theme:
        logger.error(f"No such construct: {theme_id}")
        return None

    user_id = theme["user_id"]
    prototypes = db.get_theme_prototypes(theme_id)
    if not prototypes:
        logger.warning(f"Construct {theme_id} has no prototypes to match against")
        return None

    space = ComparisonSpace(user_id)
    _, match_threshold, _ = space.space()

    # Rebuilt from the prototypes rather than read from the row: the stored
    # centroid is a convenience, the owner's sentences are the source of truth.
    vectors = [p["vector"] for p in prototypes if p["vector"] is not None]
    if not vectors:
        logger.warning(f"Construct {theme_id} has prototypes but no vectors")
        return None
    centroid = np.mean([_as_vector(v) for v in vectors], axis=0)
    centroid_in_space = space.project(centroid, are_centroids=True)[0]

    # An entry a prototype was quoted from is proven by the citation itself —
    # the quote was checked character for character against that entry's stored
    # text. Making it clear a similarity bar as well would let a construct fail
    # to include the very sentences it was built from.
    #
    # Keyed on (source_type, source_id), because a bare number is not an
    # identity: import_item 158 and reflection 158 are unrelated pieces of
    # writing, and on this archive 15 staged ids also name a reflection. Keying
    # on the number alone forced 12 unrelated reflections into candidates 33 and
    # 35 — entries scoring below the bar, cited by nothing, admitted purely by
    # numeric coincidence. Only reflections can seed: a staged recording carries
    # no date, and an occurrence needs a day it happened on (ADR-0013).
    cited = {(p["source_type"], p["source_id"]) for p in prototypes
             if p["source_id"] is not None and p["source_type"] == "reflection"}

    entries = db.get_entries_with_vectors(user_id)
    found = []
    for entry in entries:
        entry_in_space = space.project(entry["vector"])[0]
        similarity = float(centroid_in_space @ entry_in_space)
        seeded = (entry["source_type"], entry["source_id"]) in cited
        if not seeded and similarity < match_threshold:
            continue
        found.append({
            "source_type": entry["source_type"],
            "source_id": entry["source_id"],
            "snippet": (entry.get("content") or "")[:500],
            "similarity_score": similarity,
            "occurred_at": (moment.isoformat()
                            if (moment := entry.get("occurred_at")) else None),
            # A sentence the owner read and vouched for, or a match the detector
            # proposed and they never saw. Confirming a claim and authorising a
            # detector are different acts, so the evidence records which one
            # produced each row.
            "admission_basis": "citation" if seeded else "similarity",
        })
    return found


def _as_vector(value) -> np.ndarray:
    """pgvector hands a vector back as a string on some paths, a list on others."""
    if isinstance(value, str):
        return np.fromstring(value.strip("[]"), sep=",", dtype=np.float64)
    return np.asarray(value, dtype=np.float64)
