"""
Persistence Engine - Tracks What Keeps Coming Back

This module detects semantic repetition in journal entries and conversations.
It answers: "What ideas or themes keep coming back?"

The engine does not judge. It simply surfaces persistence.
- Semantic: detects meaning, not keywords
- Time-aware: tracks when themes recur
- Evidence-backed: links to actual entries
- Neutral: no analysis, no advice, just observation
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from .comparison import ComparisonSpace
from .confidence import ConfidenceEngine
from .timeutils import to_utc, utc_now
from .constants import (
    CONFIDENCE_CACHE_TTL_HOURS,
    PERSISTENCE_MATCH_THRESHOLD,
    PERSISTENCE_MIN_CLUSTER_SIZE,
)
from .database import db

from .evidence import EvidenceEngine



logger = logging.getLogger(__name__)

def confidence_is_fresh(conf: dict | None) -> bool:
    """Whether a stored theme confidence can still be served.

    Missing, explicitly invalidated (a null timestamp), or older than
    CONFIDENCE_CACHE_TTL_HOURS means recompute. It used to be served for as long
    as a timestamp existed at all.
    """
    if not conf or conf.get("last_computed_at") is None:
        return False
    age = utc_now() - to_utc(conf["last_computed_at"])
    return age <= timedelta(hours=CONFIDENCE_CACHE_TTL_HOURS)


def entry_snippet(source_type: str, source_id: int, max_length: int = 200) -> str:
    """The owner's own words from an entry, for quoting back to them.

    Every occurrence writer must use this rather than trimming the text it was
    handed. The ingest pipeline hands over the text that was *embedded*, which
    wraps a reflection in "Anchor: Self-Reflection | ... | Mood: okay ... |
    Content: ..." — so snipping it stored application metadata, and an invented
    mood, as a quote. The cluster path had already learned this; the online
    matcher and the construct classifier had not, and 47 snippets from one day's
    ingest came out wrapped.
    """
    item = db.get_memory_item(source_type, source_id)
    if item and item.get("text"):
        return " ".join(item["text"].split())[:max_length]
    # A source the memory lookup does not know: fall back rather than lose the
    # quote entirely.
    text = db.get_content_for_source(source_type, source_id)
    return text[:max_length] if text else ""


#: Sorts alongside real timestamps in the undated arm of a sort key, where the
#: leading flag has already separated dated from undated. Never read as a date.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# Complete-linkage clustering from scikit-learn (ADR-0014).
try:
    from sklearn.cluster import AgglomerativeClustering
except ImportError:
    AgglomerativeClustering = None
    logger.warning("scikit-learn clustering unavailable. Theme discovery is disabled.")


class PersistenceEngine:
    """
    Tracks what keeps coming back by finding semantic themes in journal entries.

    Core principle: An entry is assigned if it appears in theme_occurrences.
    One entry matches at most one theme: the closest one.
    """

    def __init__(self, user_id: int):
        """Initialize the persistence engine for a user."""
        self.user_id = user_id
        self.similarity_threshold = PERSISTENCE_MATCH_THRESHOLD
        self.min_cluster_size = PERSISTENCE_MIN_CLUSTER_SIZE
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence = []
        # Read through this module's own `db` name, which is the seam the
        # theme-style tests replace with a synthetic journal.
        self._comparison = ComparisonSpace(
            user_id, read_style=lambda uid: db.get_evidence_style(uid))

    # === The space themes are compared in ===

    def _space(self) -> tuple:
        """(mean, match_threshold, cluster_threshold) — see agent/comparison.py.

        Constructs compare against the same space, so it lives in one module
        used by both rather than a copy in each that can drift apart.
        """
        return self._comparison.space()

    def _project(self, vectors, are_centroids: bool = False) -> np.ndarray:
        """Unit vectors in the comparison space (agent/comparison.py)."""
        return self._comparison.project(vectors, are_centroids=are_centroids)

    def emit_evidence(self, ev_type: str, key: str, value: Any):
        """Buffers evidence for later persistence."""
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    # === Real-time Detection ===

    def check_persistence(self, embedding: list, source_type: str,
                         source_id: int, content: str,
                         occurred_at: datetime | None) -> int | None:
        """
        Called by pipeline for each new entry.
        Checks if this content matches any existing theme.
        First match above threshold wins (one entry → one theme max).

        Args:
            embedding: The embedding vector (1536-dim)
            source_type: 'reflection' or 'habit_completion'
            source_id: ID of the source entry
            content: The text content
            occurred_at: When this occurred

        Returns:
            The matched theme_id if found, else None
        """
        user_themes = self._get_user_themes()
        if not user_themes:
            return None

        _, match_threshold, _ = self._space()
        entry = self._project(embedding)[0]
        # A theme with no stored centroid cannot be compared against. Filtered
        # rather than projected: an empty list projects to a zero-dimension
        # array, and the failure then surfaces as a matmul shape error deep in
        # numpy rather than as "there was nothing to match".
        comparable = [t for t in user_themes if t.get("centroid_embedding") is not None]
        if not comparable:
            logger.info(f"No comparable themes for user {self.user_id}; nothing to match")
            return None
        centroids = self._project([t["centroid_embedding"] for t in comparable], are_centroids=True)
        similarities = centroids @ entry

        # The closest theme, not the first past the bar. Themes come back
        # largest first, so "first match wins" gave every borderline entry to
        # the biggest theme, which made the biggest theme bigger (ADR-0014).
        best = int(np.argmax(similarities))
        similarity = float(similarities[best])
        if similarity < match_threshold:
            return None

        theme = comparable[best]
        # An entry with no date still matches on what it says, and is still an
        # occurrence. It is stored without a timestamp rather than with a
        # stand-in, which keeps it out of every window engine and inside the
        # count (ADR-0013). The timestamp is passed through as it arrived, not
        # normalised: this path has always written what the caller gave it, and
        # changing that here would silently re-interpret every stored naive
        # timestamp as UTC.
        db.add_theme_occurrence(
            theme_id=theme["id"],
            source_type=source_type,
            source_id=source_id,
            snippet=entry_snippet(source_type, source_id),
            similarity_score=similarity,
            occurred_at=occurred_at.isoformat() if occurred_at else None,
        )
        db.update_theme_stats(theme["id"], occurred_at.isoformat() if occurred_at else None)
        logger.info(f"Matched entry {source_id} to theme {theme['id']} "
                   f"(similarity: {similarity:.3f})")
        return theme["id"]

    # === Theme Discovery ===

    def discover_themes(self) -> list[dict]:
        """
        Clusters unassigned entries to find new themes.
        Run periodically or on-demand.

        Returns:
            List of newly created themes
        """
        if AgglomerativeClustering is None:
            logger.error("scikit-learn clustering unavailable. Cannot discover themes.")
            return []

        # 1. Get entries not yet assigned to any theme
        unassigned = db.get_unassigned_embeddings(self.user_id)
        if len(unassigned) < self.min_cluster_size:
            logger.info(f"Not enough unassigned entries ({len(unassigned)}) "
                       f"for theme discovery (min: {self.min_cluster_size})")
            return []

        logger.info(f"Discovering themes from {len(unassigned)} unassigned entries")

        # 2. Extract embeddings and metadata
        vectors = []
        entries = []
        for item in unassigned:
            vectors.append(item["vector"])
            entries.append({
                "source_type": item["source_type"],
                "source_id": item["source_id"],
                # The event time, not the embedding time — and no fallback
                # between them. This read `... or item["created_at"]`, which
                # was invisible while every entry had a date and, the moment
                # undated ones existed, dated four of them to the second they
                # were embedded: two clustered themes then recorded a span
                # starting today for writing with no date at all. That is the
                # substitution ADR-0013 forbids, arriving as a default. None
                # stays None and the cluster simply contributes no bound.
                "occurred_at": item.get("occurred_at"),
            })

        vectors_array = np.array(vectors, dtype=np.float32)

        # 3. Cluster
        try:
            _, match_threshold, cluster_threshold = self._space()
            normalized_vectors = self._project(vectors_array)

            # Complete linkage: a cluster forms only where *every* pair of its
            # entries clears the creation bar, so it cannot chain. DBSCAN linked
            # A to B and B to C, and the cohesion check below then threw the
            # whole chain away. On the owner's journal, re-embedding three
            # entries bridged two good themes into a chain of 21 that was
            # rejected outright, leaving 25 of 138 entries grouped; dropping any
            # single entry changed how many themes formed in 75 of 138 runs.
            # With complete linkage: 74 grouped, and 18 of 138 (ADR-0014).
            cluster_labels = np.full(len(normalized_vectors), -1)
            usable = np.where(np.linalg.norm(normalized_vectors, axis=1) > 0)[0]
            if len(usable) >= 2:
                clusterer = AgglomerativeClustering(
                    n_clusters=None,
                    metric="cosine",
                    linkage="complete",
                    distance_threshold=1.0 - cluster_threshold,
                )
                cluster_labels[usable] = clusterer.fit_predict(normalized_vectors[usable])
            logger.info(f"Complete-linkage clustering found {len(set(cluster_labels) - {-1})} groups")
        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            return []

        # 4. Create themes from clusters
        new_themes = []
        unique_labels = set(cluster_labels)
        for label in unique_labels:
            if label == -1:  # Skip noise points
                continue

            cluster_indices = np.where(cluster_labels == label)[0]
            if len(cluster_indices) < 2:
                continue  # a single entry is not a pattern
            cluster_vectors = vectors_array[cluster_indices]
            cluster_entries = [entries[i] for i in cluster_indices]

            # Density clustering chains: neighbouring points can link a cluster
            # together without the two ends of it resembling each other at all.
            # The backend's own acceptance is therefore not enough to call the
            # result a theme, and the two backends are tuned differently.
            if not self._is_cohesive(normalized_vectors[cluster_indices], match_threshold):
                logger.info(
                    f"Cluster {label} rejected: not semantically cohesive "
                    f"({len(cluster_indices)} entries)"
                )
                continue

            # Improved 2: Proto-Theme Logic
            # We create the theme regardless of size here, but downstream logic will filter it
            # if it's too small. This allows "Proto-Buckets".
            theme = self._create_theme_from_cluster(cluster_vectors, cluster_entries)
            if theme:
                new_themes.append(theme)

        logger.info(f"Discovered {len(new_themes)} new themes")
        return new_themes

    def rebuild_themes(self) -> dict:
        """Regroup all of this user's evidence from scratch.

        Themes are derived: occurrences point at entries that stay where they
        are, so themes can be thrown away and found again whenever the way they
        are found changes. One clustering pass over everything, then every entry
        still ungrouped is offered to the themes that formed, oldest first, as
        the ingest path would. Theme ids change, and the analyses cached against
        the old ids are deleted with them.
        """
        removed = db.delete_user_themes(self.user_id)
        self._comparison.invalidate()
        created = self.discover_themes()

        # Oldest first, with undated entries last. They have no place in the
        # ordering because they have no date; sorting them against one would
        # have compared None with a datetime and raised, and giving them a
        # stand-in date to sort by is the substitution ADR-0013 forbids.
        leftovers = sorted(
            db.get_unassigned_embeddings(self.user_id),
            key=lambda row: (row["occurred_at"] is None, to_utc(row["occurred_at"]) or _EPOCH),
        )
        matched = 0
        for row in leftovers:
            content = db.get_content_for_source(row["source_type"], row["source_id"]) or ""
            if self.check_persistence(row["vector"], row["source_type"], row["source_id"],
                                      content, to_utc(row["occurred_at"])):
                matched += 1
        return {"removed": removed, "created": len(created),
                "matched_afterwards": matched, "ungrouped": len(leftovers) - matched}

    def _create_theme_from_cluster(self, vectors: np.ndarray,
                                  entries: list[dict]) -> dict | None:
        """
        Creates a theme from a cluster of vectors.

        Args:
            vectors: Cluster vectors (N x 1536)
            entries: Entry metadata corresponding to each vector

        Returns:
            Created theme dict or None on error
        """
        # Compute centroid
        centroid = np.mean(vectors, axis=0)

        # Earliest and latest *event* times, so a theme is dated by when its
        # entries happened rather than by when the queue got to them.
        #
        # Entries with no date contribute no bound. A cluster made entirely of
        # them has no span at all: the columns are NOT NULL so they take a
        # placeholder, and span_is_undated says that placeholder means nothing
        # — the same arrangement constructs promoted from undated writing
        # already use (migration 0011).
        # The span is derived from the occurrences when they are written; all
        # that is needed here is whether any of them carry a date at all.
        timestamps = [t for t in (to_utc(e["occurred_at"]) for e in entries) if t]
        undated_span = not timestamps

        # Generate theme summary (use LLM to create neutral summary)
        try:
            summary = self._generate_theme_summary(entries)
        except Exception as e:
            logger.error(f"Failed to generate theme summary: {e}")
            # Improved 6: Fallback to longest snippet
            summary = self._get_best_fallback_summary(entries)

        # The theme and the evidence it was made of, in one transaction. This
        # used to write the theme, then each occurrence separately, and catch
        # whatever failed: a half-built cluster stayed in the database, counted
        # by every reader, while the caller returned None and the queue retired
        # the job as done. A failure now writes nothing and reaches the worker,
        # which retries — and a replay is a no-op, since an occurrence is
        # unique per (theme, source).
        centroid_in_space = self._project(centroid, are_centroids=True)[0]
        members_in_space = self._project(vectors)
        members = []
        for i, entry in enumerate(entries):
            # Without the source type this fell back to 'journal_entry' for
            # every source, so a reflection quoted whatever journal row
            # happened to share its numeric id.
            moment = to_utc(entry.get("occurred_at"))
            members.append({
                "source_type": entry["source_type"],
                "source_id": entry["source_id"],
                "snippet": self._get_entry_snippet(entry["source_id"], entry["source_type"]),
                "similarity_score": float(centroid_in_space @ members_in_space[i]),
                "occurred_at": moment.isoformat() if moment else None,
            })

        theme_id = db.create_theme_with_occurrences(
            user_id=self.user_id,
            centroid_embedding=centroid.tolist(),
            summary=summary,
            occurrences=members,
            span_is_undated=undated_span,
        )

        logger.info(f"Created theme {theme_id} with {len(members)} initial occurrences")
        return {
            "id": theme_id,
            "summary": summary,
            "occurrence_count": len(members),
        }

    def _generate_theme_summary(self, entries: list[dict]) -> str:
        """
        Generate a brief, neutral summary of what a theme is about.
        Uses the LLM once per theme creation.

        Args:
            entries: List of entry metadata

        Returns:
            A short summary (5-10 words)
        """
        # The owner's words, not the embedding wrapper, and enough of them to
        # name a subject. Three 150-character prefixes of "Anchor:
        # Self-Reflection | Source: Reflection | Mood: okay | Content: ..." is
        # how every theme came to be called "Routine self-reflection on ...".
        snippets = []
        for entry in entries[:8]:
            item = db.get_memory_item(entry["source_type"], entry["source_id"])
            text = (item or {}).get("text") or ""
            if text:
                snippets.append(" ".join(text.split())[:400])

        if not snippets:
            return "Recurring theme"

        # Use LLM to summarize
        from .intelligence import Intelligence
        intelligence = Intelligence()

        prompt = f"""These journal excerpts share a common subject.
Name that subject in 3-8 words, as a neutral noun phrase.

Name what the writing is ABOUT — the work, the sleep, the money, the person,
the decision. Do NOT describe the act of writing: never use the words journal,
entry, reflection, self-reflection, note, writing, thoughts or musings.
Do not interpret, judge, or advise.

Excerpts:
{chr(10).join(f'- "{s}"' for s in snippets)}

Subject:"""

        try:
            messages = [{"role": "user", "content": prompt}]
            summary = intelligence.chat(
                messages=messages,
                system_prompt="You are a neutral observer. Describe patterns without judgment.",
                temperature=0.5,
                # Not 20. A reasoning model spends its budget thinking first and
                # returned an empty summary at that cap; the prompt asks for
                # 5-10 words, so brevity comes from the instruction, not the cap.
                max_tokens=400
            )
            clean_summary = summary.strip().strip('"')
            if "Recurring theme" in clean_summary or len(clean_summary) < 3:
                return self._get_best_fallback_summary(entries)
            # A name about journaling is not a name for a theme; the words below
            # describe the act, not the subject, and produced titles like
            # "Daily self-reflection on accomplishments and progress".
            meta = ("journal", "entry", "entries", "reflection", "reflections",
                    "self-reflection", "note", "notes", "writing", "musings")
            if any(word in clean_summary.lower() for word in meta):
                logger.info(f"Theme name describes journaling, retrying: {clean_summary!r}")
                retry = intelligence.chat(
                    messages=[{"role": "user", "content": prompt + (
                        "\n\nYour previous answer named the act of writing rather than "
                        "the subject. Name only the subject.")}],
                    system_prompt="You are a neutral observer. Describe patterns without judgment.",
                    temperature=0.5,
                    max_tokens=400,
                ).strip().strip('"')
                if retry and not any(word in retry.lower() for word in meta):
                    return retry
            return clean_summary
        except Exception as e:
            logger.error(f"LLM summary generation failed: {e}")
            return self._get_best_fallback_summary(entries)

    def _get_best_fallback_summary(self, entries: list[dict]) -> str:
        """Pick the longest/most descriptive snippet as the title."""
        best_snippet = "Recurring theme"
        max_len = 0

        for entry in entries[:5]:
            # Use updated snippet fetcher
            snippet = self._get_entry_snippet(entry["source_id"], entry["source_type"])
            # Clean up the snippet (remove 'Mood:', 'Action:', etc if enriched)
            if "|" in snippet:
                parts = snippet.split("|")
                # Usually the last part is the meaningful content
                clean_content = parts[-1].strip()
                if "Notes:" in clean_content:
                    clean_content = clean_content.replace("Notes:", "").strip()
                elif "Reflection:" in clean_content:
                    clean_content = clean_content.replace("Reflection:", "").strip()

                if len(clean_content) > max_len:
                    max_len = len(clean_content)
                    best_snippet = clean_content
            else:
                if len(snippet) > max_len:
                    max_len = len(snippet)
                    best_snippet = snippet

        # Truncate if too long for a title
        if len(best_snippet) > 100:
            best_snippet = best_snippet[:97] + "..."

        return best_snippet

    # === Querying ===

    def get_persistent_themes(self, min_occurrences: int = None) -> list[dict]:
        """
        Returns themes that have recurred, sorted by occurrence count.
        Also computes and caches confidence for each theme.
        
        Improved 2 & 3: Filters proto-themes and enforces temporal density.
        """
        # Default to constants if not provided
        if min_occurrences is None:
            min_occurrences = self.min_cluster_size

        all_themes = self._get_user_themes()

        # Debug logging
        logger.info(f"Checking {len(all_themes)} themes against min_occurrences {min_occurrences}")
        for t in all_themes[:3]:
             logger.info(f"  - Theme {t['id']}: Count {t['occurrence_count']}")

        # Filter 1: Occurrence Count (Proto-Theme Gate)
        candidates = [t for t in all_themes if t["occurrence_count"] >= min_occurrences]
        logger.info(f"Candidates passing proto-filter: {len(candidates)}")

        persistent = []
        for t in candidates:
            # 1. Check cache first
            conf = db.get_confidence('theme', t['id'])

            # 2. Get Evidence (needed for temporal check anyway)
            occs = self.get_theme_evidence(t['id'])

            # Filter 2: Temporal Density (Time-Awareness)
            # Require >= 3 occurrences in last 30 days
            recent_count = 0
            now = utc_now()
            timestamps = []
            source_types = []

            for o in occs:
                dt = o['occurred_at']
                if not isinstance(dt, datetime):
                    dt = to_utc(dt)

                timestamps.append(dt)

                # Determine source type for weighting
                st = o['source_type']
                snippet = o.get('snippet', '')
                if st == 'habit_completion' and ("Notes:" in snippet or "Reason:" in snippet):
                    source_types.append('habit_completion_with_notes')
                else:
                    source_types.append(st)

                # Check recent window
                days_diff = (now - dt).days
                if days_diff <= 30:
                    recent_count += 1

            # Debug logging
            logger.info(f"Theme {t['id']}: Count {t['occurrence_count']}, Recent {recent_count}")

            # Enforce Temporal Density
            if recent_count < 3:
                logger.info(f"Theme {t['id']} SKIPPED: Low temporal density ({recent_count} < 3)")
                continue # Skip this theme, it's dormant or noise

            # If confirmed, proceed to confidence
            if not confidence_is_fresh(conf):
                conf = self._store_theme_confidence(t['id'], timestamps, source_types)

            # `confidence_level` is the key the pipeline's admission gate reads.
            # Emitting only `confidence` meant the orchestrator filled the
            # missing field with "unknown", which the gate scores below any
            # threshold — so persistence insights, however strong, were dropped
            # before reaching the LLM. `confidence` is kept for existing readers.
            t['confidence_level'] = conf['confidence_level']
            t['confidence'] = conf['confidence_level']
            t['confidence_score'] = conf['confidence_score']
            persistent.append(t)

        return persistent

    def theme_confidence(self, theme_id: int) -> dict:
        """How much evidence stands behind one theme: computed, stored, returned.

        The explanation of a theme reads this record, and the only thing that
        used to write it was the persistence *finding* — computed only for themes
        with three occurrences in the last thirty days, and only when a chat
        turn happened to run that finding. So "explain this theme" depended on
        which surface had run what, and on an archive with no recent writing it
        answered "No analytical record found." for every theme. Confidence is
        about the evidence behind a theme, not about whether it is recent, so it
        is computed here on request.
        """
        timestamps, source_types = [], []
        for o in self.get_theme_evidence(theme_id):
            timestamps.append(to_utc(o['occurred_at']))
            st, snippet = o['source_type'], o.get('snippet', '')
            if st == 'habit_completion' and ("Notes:" in snippet or "Reason:" in snippet):
                source_types.append('habit_completion_with_notes')
            else:
                source_types.append(st)
        if not timestamps:
            return {}
        return self._store_theme_confidence(theme_id, timestamps, source_types)

    def _store_theme_confidence(self, theme_id: int, timestamps: list, source_types: list) -> dict:
        # Each theme's bundle must record that theme's own metrics. The
        # buffer was initialised once per engine and only ever appended to,
        # so a run over several themes stored theme 1's numbers inside
        # theme 2's bundle and the explanation quoted the wrong evidence.
        self._evidence = []

        # Improved 5: Pass source_types for Evidence Tiering
        conf = self.conf_engine.compute_confidence(
            'theme', theme_id, timestamps, sources=source_types
        )

        # Emit raw components as evidence
        self.emit_evidence('count', 'occurrence_count', conf['data_points_count'])
        self.emit_evidence('window', 'time_coverage_days', conf['time_coverage_days'])
        self.emit_evidence('rate', 'recency_score', conf['recency_score'])

        # Store in central registry
        db.create_or_update_confidence(
            'theme', theme_id,
            conf['confidence_level'], conf['confidence_score'],
            conf['data_points_count'], conf['time_coverage_days'],
            conf['consistency_score'], conf['recency_score']
        )

        # Record evidence bundle
        self.ev_engine.record_evidence('persistence', 'theme', theme_id, self._evidence)
        return conf

    def get_theme_evidence(self, theme_id: int) -> list[dict]:
        """
        Returns all occurrences of a theme with chronological timeline.

        Args:
            theme_id: The theme to get evidence for

        Returns:
            List of occurrences with source information
        """
        return db.get_theme_occurrences(theme_id)

    def get_theme_timeline(self, theme_id: int) -> str:
        """
        Returns formatted chronological timeline of when theme appeared.

        Args:
            theme_id: The theme to get timeline for

        Returns:
            Formatted timeline string
        """
        occurrences = self.get_theme_evidence(theme_id)
        if not occurrences:
            return "No occurrences recorded."

        lines = []
        for occ in occurrences:
            # Handle both datetime objects and strings
            occurred_at = occ["occurred_at"]
            if isinstance(occurred_at, datetime):
                date_str = occurred_at.strftime("%Y-%m-%d")
            else:
                date_str = str(occurred_at).split("T")[0]

            snippet = occ["snippet"][:80] if occ["snippet"] else "(no text)"
            score = f"{occ['similarity_score']:.2f}"
            lines.append(f"  {date_str}  \"{snippet}\" (confidence: {score})")

        return "TIMELINE:\n\n" + "\n\n".join(lines)

    # === Context for LLM ===

    # === Private Helpers ===

    def _get_user_themes(self) -> list[dict]:
        """The themes an entry competes to join — clusters only.

        Topical clustering is exclusive: one entry, one cluster, the closest.
        Constructs are not part of that competition (see
        `constructs.classify`), because they are independent classifiers rather
        than rival groupings.
        """
        return db.get_themes_by_origin(self.user_id, "clustered")

    def _is_cohesive(self, vectors: np.ndarray, threshold: float | None = None) -> bool:
        """Does every member of this cluster clear the theme-creation threshold?

        Backend-independent acceptance, checked against the centroid the theme
        will actually be stored with, and stated in the same terms CONTEXT.md
        already uses: PERSISTENCE_CLUSTER_THRESHOLD forms a theme,
        PERSISTENCE_MATCH_THRESHOLD (looser) adds to an existing one. A founding
        member is held to the creation threshold.

        The check is on the cluster's *diameter*, not its average. Density
        clustering chains: A links to B and B links to C while A and C resemble
        each other not at all, and an average happily absorbs both ends of a
        chain nobody would call one pattern. Complete linkage now guarantees this
        at the creation bar, so the check is a safety net: it states what a
        theme is in one place, whatever the clustering method.
        """
        if len(vectors) < 2:
            return False

        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if float(norms.min()) == 0.0:
            return False

        unit = vectors / norms
        similarities = unit @ unit.T
        np.fill_diagonal(similarities, 1.0)

        return float(similarities.min()) >= (PERSISTENCE_MATCH_THRESHOLD if threshold is None else threshold)

    def _get_entry_snippet(self, entry_id: int, source_type: str, max_length: int = 200) -> str:
        """The owner's own words for an entry; see `entry_snippet`."""
        return entry_snippet(source_type, entry_id, max_length)

    def refresh_snippets(self) -> int:
        """Rewrite stored occurrence snippets in the owner's own words.

        Existing occurrences keep whatever snippet was stored when they were
        written, so fixing the source above does not fix what is already on
        screen.
        """
        updated = 0
        for theme in db.get_themes(self.user_id):
            # Undated occurrences included: the default read is dated-only,
            # and the rows this exists to repair were undated ones.
            for occ in db.get_theme_occurrences(theme["id"], include_undated=True):
                snippet = self._get_entry_snippet(occ["source_id"], occ["source_type"])
                if snippet and snippet != occ.get("snippet"):
                    with db.connection() as conn, conn.cursor() as cur:
                        cur.execute(
                            """UPDATE theme_occurrences SET snippet = %s
                                WHERE theme_id = %s AND source_type = %s AND source_id = %s;""",
                            (snippet, theme["id"], occ["source_type"], occ["source_id"]),
                        )
                        conn.commit()
                    updated += 1
        logger.info(f"Rewrote {updated} occurrence snippet(s) for user {self.user_id}")
        return updated
