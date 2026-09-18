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

import logging

import numpy as np

from .comparison import ComparisonSpace
from .database import db
from .pipeline import generate_embedding
from .timeutils import utc_now

logger = logging.getLogger(__name__)

#: A construct needs a name short enough to read on a card. The claim is kept
#: whole in `definition`; this is only what the engines print.
SUMMARY_MAX_CHARS = 72


def _summarise(claim: str) -> str:
    """A card-sized name for the pattern, cut at a word boundary."""
    text = " ".join((claim or "").split())
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    cut = text[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0]
    return (cut or text[:SUMMARY_MAX_CHARS]).rstrip(" ,.;:") + "…"


def promote(user_id: int, observation) -> int | None:
    """Store a discovered observation as a candidate construct.

    Returns the theme id, or None if the observation carried nothing that could
    anchor it. Nothing is measured as a result of this call.
    """
    citations = list(getattr(observation, "citations", ()) or ())
    if not citations:
        logger.warning("Refusing to promote an observation with no citations")
        return None

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
    dates = [c.entry_date for c in citations if getattr(c, "entry_date", None)]
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
    )

    for citation, vector in prototypes:
        db.add_theme_prototype(
            theme_id=theme_id,
            source_type=getattr(citation, "source_type", "reflection"),
            source_id=getattr(citation, "entry_id", None),
            quote=citation.text,
            vector=vector,
        )

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
            "spanStart": _iso(theme["first_seen_at"]),
            "spanEnd": _iso(theme["last_seen_at"]),
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
    observations = engine.read_archive(include_staged=include_staged)
    for observation in observations:
        promote(user_id, observation)
    logger.info(f"Discovery staged {len(observations)} candidate(s) for user {user_id}")
    return candidates(user_id)


def reject(theme_id: int) -> None:
    """The owner did not recognise this. It is kept, and never measured."""
    db.set_theme_status(theme_id, "rejected")
    logger.info(f"Construct {theme_id} rejected")


def confirm(theme_id: int) -> int:
    """The owner vouched for this. Measure it against the whole archive."""
    db.set_theme_status(theme_id, "active")
    written = scan(theme_id)
    logger.info(f"Construct {theme_id} confirmed, {written} occurrence(s) found")
    return written


def scan(theme_id: int) -> int:
    """Find every entry this construct describes, and record each one.

    Compares each evidence-eligible entry against the construct's centroid in
    the shared comparison space, at the same threshold clustering uses, and
    writes matches through the ordinary occurrence path so the existing engines
    pick them up unchanged.
    """
    theme = db.get_theme_by_id(theme_id)
    if not theme:
        logger.error(f"No such construct: {theme_id}")
        return 0

    user_id = theme["user_id"]
    prototypes = db.get_theme_prototypes(theme_id)
    if not prototypes:
        logger.warning(f"Construct {theme_id} has no prototypes to match against")
        return 0

    space = ComparisonSpace(user_id)
    _, match_threshold, _ = space.space()

    # Rebuilt from the prototypes rather than read from the row: the stored
    # centroid is a convenience, the owner's sentences are the source of truth.
    vectors = [p["vector"] for p in prototypes if p["vector"] is not None]
    if not vectors:
        logger.warning(f"Construct {theme_id} has prototypes but no vectors")
        return 0
    centroid = np.mean([_as_vector(v) for v in vectors], axis=0)
    centroid_in_space = space.project(centroid, are_centroids=True)[0]

    # An entry a prototype was quoted from is proven by the citation itself —
    # the quote was checked character for character against that entry's stored
    # text. Making it clear a similarity bar as well would let a construct fail
    # to include the very sentences it was built from.
    cited = {p["source_id"] for p in prototypes if p["source_id"] is not None}

    entries = db.get_entries_with_vectors(user_id)
    written = 0
    for entry in entries:
        entry_in_space = space.project(entry["vector"])[0]
        similarity = float(centroid_in_space @ entry_in_space)
        if entry["source_id"] not in cited and similarity < match_threshold:
            continue
        db.add_theme_occurrence(
            theme_id=theme_id,
            source_type=entry["source_type"],
            source_id=entry["source_id"],
            snippet=(entry.get("content") or "")[:500],
            similarity_score=similarity,
            occurred_at=entry["occurred_at"].isoformat(),
        )
        written += 1

    db.update_theme_stats(theme_id)
    return written


def _as_vector(value) -> np.ndarray:
    """pgvector hands a vector back as a string on some paths, a list on others."""
    if isinstance(value, str):
        return np.fromstring(value.strip("[]"), sep=",", dtype=np.float64)
    return np.asarray(value, dtype=np.float64)
