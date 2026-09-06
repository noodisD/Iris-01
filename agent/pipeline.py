"""
Processing Pipeline Layer

This module orchestrates the expensive and potentially fallible processing
of raw data after it has been safely stored in PostgreSQL. It's responsible
for generating embeddings and clustering entries into persistent themes.
"""

import logging

import openai
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .timeutils import to_utc, utc_now
from .config import settings

# Import the data layer interfaces
from .database import embeddings
from .persistence import PersistenceEngine

logger = logging.getLogger(__name__)

# Configure OpenAI client
openai.api_key = settings.OPENAI_API_KEY

# Retry only on transient OpenAI errors (rate limits, timeouts, 5xx).
# Auth errors and bad requests are not retried — they won't succeed on retry.
_TRANSIENT_OPENAI_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_TRANSIENT_OPENAI_ERRORS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def generate_embedding(text: str, model: str = "text-embedding-3-small") -> list:
    """
    Generates an embedding for a given text using the OpenAI API.
    Retries up to 4 times on transient errors with exponential backoff.
    """
    text = text.replace("\n", " ")
    try:
        response = openai.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except _TRANSIENT_OPENAI_ERRORS:
        raise  # let tenacity handle
    except Exception as e:
        logger.error(f"Failed to generate embedding (non-retryable): {e}")
        raise

def extract_entities(text: str) -> dict:
    """
    A simple placeholder for extracting structured entities from raw text.
    In a real app, this could be a call to a local NLP model or another LLM.
    """
    ideas = [line.strip().lstrip('- ') for line in text.split('\n') if line.strip().startswith('- ')]
    return {"ideas": ideas}

def _refresh_cross_theme_analyses(user_id: int) -> None:
    """Recompute leverage and decision impact for a user, into their caches.

    These two engines are pairwise (O(themes^2)) and, unlike the others, do not
    cache on read — `force_recompute` is accepted and ignored, so every call
    recomputes from occurrences. The chat path therefore reads their cache
    tables directly, which stays fast but means nothing filled those tables on
    the HTTP path: only the Insights screen and the CLI ever ran the engines, so
    two of the six engines were silent in the chat context unless the user
    happened to open Insights first.

    Recomputing here, where an occurrence has just changed the theme graph (and
    where add_theme_occurrence has just invalidated these very caches), keeps
    the chat path reading warm data without paying O(n^2) per message.
    """
    from .decision_impact import DecisionImpactEngine
    from .leverage import LeverageEngine

    try:
        LeverageEngine(user_id).analyze_all_leverage()
        DecisionImpactEngine(user_id).analyze_all_anchors()
    except Exception as e:
        # Non-blocking: the entry is already stored, and a stale cross-theme
        # cache is a worse-context problem, not a data problem.
        logger.warning(f"Cross-theme refresh failed for user {user_id}: {e}")


def run_processing_pipeline(source_type: str, source_id: int):
    """
    Runs the full processing pipeline for a given source item.
    This function is the core of the orchestration layer.
    """
    logger.info(f"Starting processing pipeline for {source_type} ID: {source_id}")

    try:
        # 1. Update status to 'processing'
        embeddings.update_processing_status(source_type, source_id, 'processing')

        # 2. Fetch the raw content from PostgreSQL — by id, not "any row in
        # this status". Filtering on status alone let a concurrent write, or a
        # row left behind by a crashed run, be picked up instead: that row's
        # text was embedded under this source_id, carrying its user_id with it.
        item = embeddings.get_items_to_process(
            source_type, status='processing', limit=1, source_id=source_id
        )
        if not item:
            logger.warning(f"Could not find {source_type} ID {source_id} to process.")
            return

        item_data = item[0]
        if item_data["id"] != source_id:
            logger.error(
                f"Refusing to process {source_type} {source_id}: fetched row "
                f"{item_data['id']}. Aborting rather than mis-attributing content."
            )
            return
        content = item_data['content']
        user_id = item_data['user_id']
        occurred_at = item_data['occurred_at']

        # Backfill detection logging. to_utc() handles strings, dates and both
        # flavours of datetime, so the branching this used to need is gone.
        try:
            dt_occ = to_utc(occurred_at)
            if dt_occ and (utc_now() - dt_occ).days > 1:
                logger.info(f"Processing historical item from {dt_occ} (Backfill detected)")
        except Exception as e:
            logger.warning(f"Timestamp check failed: {e}")

        # 3. Generate embedding
        model_name = "text-embedding-3-small"
        embedding = generate_embedding(content, model=model_name)

        # 4. Store the canonical embedding in PostgreSQL
        embeddings.add_embedding(source_type, source_id, model_name, embedding)

        # 5. Check for persistence (what keeps coming back)
        # User messages participate in theme matching; assistant responses are excluded
        # to avoid amplifying theme signals with derivative content.
        # Chat messages are embedded for semantic retrieval but are NOT theme
        # occurrences. CONTEXT.md defines an occurrence as a journal entry,
        # reflection or habit completion, and EVIDENCE_WEIGHTS has no entry for
        # messages (they silently took the 0.5 default meant for a bare habit
        # tick). Counting them let a theme resurrect itself mid-request:
        # mentioning a dissipated pattern in chat created a fresh occurrence,
        # which invalidated the resolution cache, so the label recomputed to
        # 'persisting' before the narrative for that same turn was written.
        should_check_persistence = source_type in ['journal_entry', 'reflection', 'habit_completion']
        if should_check_persistence:
            try:
                engine = PersistenceEngine(user_id)
                matched_theme_id = engine.check_persistence(
                    embedding=embedding,
                    source_type=source_type,
                    source_id=source_id,
                    content=content,
                    occurred_at=occurred_at
                )
                if matched_theme_id:
                    logger.info(f"{source_type.capitalize()} {source_id} matched theme {matched_theme_id}")
                    _refresh_cross_theme_analyses(user_id)
                else:
                    # Nothing matched. Themes are only *born* from clustering,
                    # and discover_themes() used to be reachable only from the
                    # CLI — so a user of the web app never formed a first theme
                    # and the whole analytical product (trajectories, tensions,
                    # resolutions, insights) stayed permanently empty.
                    # discover_themes() returns early when there is less
                    # unassigned material than the proto-theme threshold, so
                    # this costs one query on most writes.
                    new_themes = engine.discover_themes()
                    if new_themes:
                        logger.info(
                            f"Discovery created {len(new_themes)} new theme(s) "
                            f"after {source_type} {source_id}"
                        )
                        _refresh_cross_theme_analyses(user_id)
            except Exception as e:
                logger.error(f"Persistence check failed for {source_type} ID {source_id}: {e}")
                # Non-blocking: don't fail the pipeline if persistence fails

        # 6. Update status to 'complete'
        embeddings.update_processing_status(source_type, source_id, 'complete')
        logger.info(f"Successfully completed processing for {source_type} ID: {source_id}")

    except Exception as e:
        logger.error(f"Processing pipeline failed for {source_type} ID {source_id}: {e}")
        embeddings.update_processing_status(source_type, source_id, 'failed')
        # Optionally, re-raise the exception if the caller needs to handle it
        # raise
