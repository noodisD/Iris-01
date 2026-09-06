"""
Processing Pipeline Layer

This module orchestrates the expensive and potentially fallible processing
of raw data after it has been safely stored in PostgreSQL. It's responsible
for generating embeddings and clustering entries into persistent themes.
"""

import logging
import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
from .config import settings

# Import the data layer interfaces
from .database import db, embeddings
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

def run_processing_pipeline(source_type: str, source_id: int):
    """
    Runs the full processing pipeline for a given source item.
    This function is the core of the orchestration layer.
    """
    logger.info(f"Starting processing pipeline for {source_type} ID: {source_id}")

    try:
        # 1. Update status to 'processing'
        embeddings.update_processing_status(source_type, source_id, 'processing')

        # 2. Fetch the raw content from PostgreSQL
        item = embeddings.get_items_to_process(source_type, status='processing', limit=1)
        if not item:
            logger.warning(f"Could not find {source_type} ID {source_id} to process.")
            return
        
        item_data = item[0]
        content = item_data['content']
        user_id = item_data['user_id']
        occurred_at = item_data['occurred_at']

        # Backfill detection logging
        try:
            from datetime import datetime
            if isinstance(occurred_at, str):
                dt_occ = datetime.fromisoformat(occurred_at)
            else:
                dt_occ = occurred_at
            
            # Use hasattr to safely check for tzinfo (date objects don't have it)
            if dt_occ and hasattr(dt_occ, 'tzinfo') and dt_occ.tzinfo:
                dt_occ = dt_occ.replace(tzinfo=None)
                
            # Convert date to datetime for comparison if needed
            from datetime import date
            if isinstance(dt_occ, date) and not isinstance(dt_occ, datetime):
                dt_comp = datetime.combine(dt_occ, datetime.min.time())
            else:
                dt_comp = dt_occ

            if dt_comp and (datetime.now() - dt_comp).days > 1:
                logger.info(f"Processing historical item from {dt_comp} (Backfill detected)")
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
