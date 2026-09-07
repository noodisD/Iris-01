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
from datetime import datetime
from typing import Any

# Attempt to import sklearn, but handle gracefully if unavailable
try:
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    cosine_similarity = None
    SKLEARN_AVAILABLE = False

import numpy as np

from .confidence import ConfidenceEngine
from .timeutils import to_utc, utc_now
from .constants import (
    PERSISTENCE_CLUSTER_THRESHOLD,
    PERSISTENCE_MATCH_THRESHOLD,
    PERSISTENCE_MIN_CLUSTER_SIZE,
)
from .database import confidence as confidence_repo

# Import repositories and constants
from .database import embeddings, themes
from .evidence import EvidenceEngine


def cosine_similarity_manual(vec1, vec2):
    """
    Calculate cosine similarity manually without sklearn.
    This function computes the cosine similarity between two vectors.
    """
    # Convert to numpy arrays if they aren't already
    v1 = np.array(vec1).flatten()
    v2 = np.array(vec2).flatten()

    # Calculate dot product
    dot_product = np.dot(v1, v2)

    # Calculate magnitudes
    magnitude_v1 = np.sqrt(np.sum(v1 ** 2))
    magnitude_v2 = np.sqrt(np.sum(v2 ** 2))

    # Handle zero magnitude cases
    if magnitude_v1 == 0 or magnitude_v2 == 0:
        return 0.0

    # Calculate cosine similarity
    similarity = dot_product / (magnitude_v1 * magnitude_v2)
    return similarity

logger = logging.getLogger(__name__)

# Try to import hdbscan, with fallback to scikit-learn alternatives
try:
    from hdbscan import HDBSCAN
    HAS_HDBSCAN = True
    CLUSTERING_BACKEND = "hdbscan"
except ImportError:
    HAS_HDBSCAN = False
    logger.info("hdbscan not installed. Will use scikit-learn clustering as fallback.")

    # Try to use scikit-learn clustering algorithms as fallback
    try:
        from sklearn.cluster import DBSCAN
        HAS_DBSCAN = True
        CLUSTERING_BACKEND = "dbscan"
    except ImportError:
        HAS_DBSCAN = False
        logger.warning("Neither hdbscan nor DBSCAN available. Theme discovery will be limited.")
        CLUSTERING_BACKEND = "none"


class PersistenceEngine:
    """
    Tracks what keeps coming back by finding semantic themes in journal entries.

    Core principle: An entry is assigned if it appears in theme_occurrences.
    One entry matches at most one theme (first match wins).
    """

    def __init__(self, user_id: int):
        """Initialize the persistence engine for a user."""
        self.user_id = user_id
        self.similarity_threshold = PERSISTENCE_MATCH_THRESHOLD
        self.min_cluster_size = PERSISTENCE_MIN_CLUSTER_SIZE
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence = []

    def emit_evidence(self, ev_type: str, key: str, value: Any):
        """Buffers evidence for later persistence."""
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    # === Real-time Detection ===

    def check_persistence(self, embedding: list, source_type: str,
                         source_id: int, content: str, occurred_at: datetime) -> int | None:
        """
        Called by pipeline for each new entry.
        Checks if this content matches any existing theme.
        First match above threshold wins (one entry → one theme max).

        Args:
            embedding: The embedding vector (1536-dim)
            source_type: 'journal_entry' or 'message'
            source_id: ID of the source entry
            content: The text content
            occurred_at: When this occurred

        Returns:
            The matched theme_id if found, else None
        """
        user_themes = self._get_user_themes()
        if not user_themes:
            return None

        embedding_array = np.array(embedding, dtype=np.float32).reshape(1, -1)

        for theme in user_themes:
            centroid = np.array(theme["centroid_embedding"], dtype=np.float32).reshape(1, -1)

            if SKLEARN_AVAILABLE:
                similarity = cosine_similarity(embedding_array, centroid)[0][0]
            else:
                # Use manual cosine similarity calculation
                similarity = cosine_similarity_manual(embedding_array[0], centroid[0])

            # Improved 1: Use dual thresholds. Matching is easier (0.70) than creating.
            if similarity >= self.similarity_threshold:
                # Record occurrence and update stats
                snippet = self._extract_snippet(content)
                themes.add_occurrence(
                    theme_id=theme["id"],
                    source_type=source_type,
                    source_id=source_id,
                    snippet=snippet,
                    similarity_score=float(similarity),
                    occurred_at=occurred_at.isoformat()
                )
                themes.update_stats(theme["id"], occurred_at.isoformat())
                logger.info(f"Matched entry {source_id} to theme {theme['id']} "
                           f"(similarity: {similarity:.3f})")
                return theme["id"]  # First match wins

        return None

    # === Theme Discovery ===

    def discover_themes(self) -> list[dict]:
        """
        Clusters unassigned entries to find new themes.
        Run periodically or on-demand.

        Returns:
            List of newly created themes
        """
        if not HAS_HDBSCAN and not HAS_DBSCAN:
            logger.error("Neither hdbscan nor dbscan available. Cannot discover themes.")
            return []

        # 1. Get entries not yet assigned to any theme
        unassigned = embeddings.get_unassigned_embeddings(self.user_id)
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
                "created_at": item["created_at"]
            })

        vectors_array = np.array(vectors, dtype=np.float32)

        # 3. Cluster using available algorithm
        # Normalize vectors and use euclidean (mathematically equivalent to cosine for clustering)
        # This is more robust than using the 'cosine' metric directly
        try:
            norms = np.linalg.norm(vectors_array, axis=1, keepdims=True)
            normalized_vectors = vectors_array / (norms + 1e-10)

            if CLUSTERING_BACKEND == "hdbscan":
                clusterer = HDBSCAN(
                    min_cluster_size=self.min_cluster_size,
                    min_samples=1,
                    metric='euclidean',
                    cluster_selection_method='leaf',
                    allow_single_cluster=True
                )
                cluster_labels = clusterer.fit_predict(normalized_vectors)
                logger.info(f"HDBSCAN clustering found labels: {set(cluster_labels)}")
            elif CLUSTERING_BACKEND == "dbscan":
                # Use DBSCAN as fallback - similar to HDBSCAN but with eps parameter
                from sklearn.neighbors import NearestNeighbors

                # Estimate eps based on min_cluster_size
                # Find distance to k-th nearest neighbor where k=min_cluster_size
                k = min(self.min_cluster_size, len(normalized_vectors) - 1)
                if k > 0:
                    neighbors = NearestNeighbors(n_neighbors=k).fit(normalized_vectors)
                    distances, indices = neighbors.kneighbors(normalized_vectors)
                    # Use the average distance to k-th neighbor as eps
                    avg_kth_distance = np.mean(distances[:, -1])
                    # Ensure minimum eps based on cluster threshold
                    # Cosine distance = 1 - Cosine Similarity
                    # We want similarity > 0.78, so distance < 0.22
                    eps = max(avg_kth_distance, 1.0 - PERSISTENCE_CLUSTER_THRESHOLD)
                else:
                    eps = 1.0 - PERSISTENCE_CLUSTER_THRESHOLD

                clusterer = DBSCAN(
                    eps=eps,
                    # Improved 3: Ensure we don't form singleton clusters
                    min_samples=max(2, self.min_cluster_size // 2),
                    metric='euclidean'
                )
                cluster_labels = clusterer.fit_predict(normalized_vectors)
                logger.info(f"DBSCAN clustering found labels: {set(cluster_labels)}")
            else:
                logger.error("No clustering algorithm available.")
                return []
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
            cluster_vectors = vectors_array[cluster_indices]
            cluster_entries = [entries[i] for i in cluster_indices]

            # Improved 2: Proto-Theme Logic
            # We create the theme regardless of size here, but downstream logic will filter it
            # if it's too small. This allows "Proto-Buckets".
            theme = self._create_theme_from_cluster(cluster_vectors, cluster_entries)
            if theme:
                new_themes.append(theme)

        logger.info(f"Discovered {len(new_themes)} new themes")
        return new_themes

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

        # Get earliest and latest timestamps (handle both datetime and string)
        timestamps = []
        for e in entries:
            created_at = e["created_at"]
            if isinstance(created_at, datetime):
                timestamps.append(created_at)
            else:
                timestamps.append(datetime.fromisoformat(str(created_at)))
        first_seen = min(timestamps)
        last_seen = max(timestamps)

        # Generate theme summary (use LLM to create neutral summary)
        try:
            summary = self._generate_theme_summary(entries)
        except Exception as e:
            logger.error(f"Failed to generate theme summary: {e}")
            # Improved 6: Fallback to longest snippet
            summary = self._get_best_fallback_summary(entries)

        # Create theme in database
        try:
            theme_id = themes.create_theme(
                user_id=self.user_id,
                centroid_embedding=centroid.tolist(),
                summary=summary,
                first_seen_at=first_seen.isoformat(),
                last_seen_at=last_seen.isoformat(),
                occurrence_count=len(entries)
            )

            # Record initial occurrences
            for i, entry in enumerate(entries):
                snippet = self._get_entry_snippet(entry["source_id"])

                if SKLEARN_AVAILABLE:
                    similarity = cosine_similarity(
                        centroid.reshape(1, -1),
                        vectors[i].reshape(1, -1)
                    )[0][0]
                else:
                    # Use manual cosine similarity calculation
                    similarity = cosine_similarity_manual(centroid, vectors[i])

                themes.add_occurrence(
                    theme_id=theme_id,
                    source_type=entry["source_type"],
                    source_id=entry["source_id"],
                    snippet=snippet,
                    similarity_score=float(similarity),
                    occurred_at=entry["created_at"]
                )

            logger.info(f"Created theme {theme_id} with {len(entries)} initial occurrences")
            return {
                "id": theme_id,
                "summary": summary,
                "occurrence_count": len(entries)
            }
        except Exception as e:
            logger.error(f"Failed to create theme: {e}")
            return None

    def _generate_theme_summary(self, entries: list[dict]) -> str:
        """
        Generate a brief, neutral summary of what a theme is about.
        Uses the LLM once per theme creation.

        Args:
            entries: List of entry metadata

        Returns:
            A short summary (5-10 words)
        """
        # Get actual text snippets
        snippets = []
        for entry in entries[:3]:  # Use first 3 entries for context
            text = embeddings.get_content_for_source(entry["source_type"], entry["source_id"])
            if text:
                # Truncate to first 150 chars
                snippets.append(text[:150])

        if not snippets:
            return "Recurring theme"

        # Use LLM to summarize
        from .intelligence import Intelligence
        intelligence = Intelligence()

        prompt = f"""These journal excerpts share a common semantic theme.
Create a neutral, observational summary of the theme in 5-10 words.
Do NOT interpret, judge, or offer advice.
Just name what keeps coming back.

Excerpts:
{chr(10).join(f'- "{s}"' for s in snippets)}

Theme summary:"""

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
            # Improved 6: Check for generic fallback in LLM response too
            clean_summary = summary.strip()
            if "Recurring theme" in clean_summary or len(clean_summary) < 3:
                 return self._get_best_fallback_summary(entries)
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
            conf = confidence_repo.get_confidence('theme', t['id'])

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
            if not conf or conf.get('last_computed_at') is None:
                # Improved 5: Pass source_types for Evidence Tiering
                conf = self.conf_engine.compute_confidence(
                    'theme', t['id'], timestamps, sources=source_types
                )

                # Emit raw components as evidence
                self.emit_evidence('count', 'occurrence_count', conf['data_points_count'])
                self.emit_evidence('window', 'time_coverage_days', conf['time_coverage_days'])
                self.emit_evidence('rate', 'recency_score', conf['recency_score'])

                # 3. Store in central registry
                confidence_repo.create_or_update(
                    'theme', t['id'],
                    conf['confidence_level'], conf['confidence_score'],
                    conf['data_points_count'], conf['time_coverage_days'],
                    conf['consistency_score'], conf['recency_score']
                )

                # 4. Record evidence bundle
                self.ev_engine.record_evidence('persistence', 'theme', t['id'], self._evidence)

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

    def get_theme_evidence(self, theme_id: int) -> list[dict]:
        """
        Returns all occurrences of a theme with chronological timeline.

        Args:
            theme_id: The theme to get evidence for

        Returns:
            List of occurrences with source information
        """
        return themes.get_occurrences(theme_id)

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
        """Retrieve all themes for this user."""
        return themes.get_all_themes(self.user_id)

    def _extract_snippet(self, text: str, max_length: int = 200) -> str:
        """Extract a snippet from text."""
        if not text:
            return ""
        return text[:max_length]

    def _get_entry_snippet(self, entry_id: int, source_type: str = 'journal_entry', max_length: int = 200) -> str:
        """Get snippet from a journal entry."""
        text = embeddings.get_content_for_source(source_type, entry_id)
        return self._extract_snippet(text, max_length) if text else ""
