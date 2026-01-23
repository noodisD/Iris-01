"""
Processing Pipeline Layer

This module orchestrates the expensive and potentially fallible processing
of raw data after it has been safely stored in PostgreSQL. It's responsible
for generating embeddings, extracting entities, and projecting data into the
vector and graph database lenses.
"""

import logging
import openai
from .config import settings

# Import the data layer interfaces
from .database import db
from .vector_store import vector_store
from .graph_db import graph_db
from .persistence import PersistenceEngine

logger = logging.getLogger(__name__)

# Configure OpenAI client
openai.api_key = settings.OPENAI_API_KEY

def generate_embedding(text: str, model: str = "text-embedding-3-small") -> list:
    """
    Generates an embedding for a given text using the OpenAI API.
    """
    text = text.replace("\n", " ")
    try:
        response = openai.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
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
        db.update_processing_status(source_type, source_id, 'processing')

        # 2. Fetch the raw content from PostgreSQL
        item = db.get_items_to_process(source_type, status='processing', limit=1)
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
        db.add_embedding(source_type, source_id, model_name, embedding)

        # 5. Project the embedding into the ChromaDB lens
        metadata = {"model_name": model_name}
        vector_store.add_embedding(source_id, embedding, metadata, source_type)

        # 6. Extract entities and project into the Neo4j lens
        if source_type == 'journal_entry':
            entities = extract_entities(content)

            graph_db.add_journal_entry_node(source_id, user_id, occurred_at)
            for idea in entities.get("ideas", []):
                graph_db.add_idea_node(idea)
                graph_db.link_journal_to_idea(source_id, idea)
        elif source_type == 'reflection':
            entities = extract_entities(content)

            graph_db.add_journal_entry_node(source_id, user_id, occurred_at)
            for idea in entities.get("ideas", []):
                graph_db.add_idea_node(idea)
                graph_db.link_journal_to_idea(source_id, idea)
        elif source_type == 'habit':
            name = item_data['name']
            graph_db.add_habit_node(source_id, user_id, name, occurred_at)
        elif source_type == 'habit_completion':
            habit_id = item_data['habit_id']
            graph_db.add_habit_completion_node(source_id, habit_id, user_id, occurred_at, notes=content)
        elif source_type == 'message':
            pass

        # Link same-day events in Graph to increase connectivity
        if source_type in ['journal_entry', 'reflection', 'habit_completion']:
            graph_db.link_same_day_events(source_id, source_type, occurred_at)

        # 7. Check for persistence (what keeps coming back)
        if source_type in ['journal_entry', 'reflection', 'habit_completion']:
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

        # 8. Update status to 'complete'
        db.update_processing_status(source_type, source_id, 'complete')
        logger.info(f"Successfully completed processing for {source_type} ID: {source_id}")

    except Exception as e:
        logger.error(f"Processing pipeline failed for {source_type} ID {source_id}: {e}")
        db.update_processing_status(source_type, source_id, 'failed')
        # Optionally, re-raise the exception if the caller needs to handle it
        # raise
