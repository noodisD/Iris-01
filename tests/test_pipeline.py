"""
Tests for the Processing Pipeline Layer.
"""

import pytest
from agent.pipeline import generate_embedding, extract_entities, run_processing_pipeline
from agent.database import db

def test_generate_embedding(mocker):
    """Test the embedding generation, mocking the OpenAI API call."""
    mock_openai = mocker.patch("agent.pipeline.openai.embeddings.create")
    mock_openai.return_value.data = [mocker.Mock(embedding=[0.1] * 1536)]
    
    embedding = generate_embedding("test text")
    
    mock_openai.assert_called_once()
    assert isinstance(embedding, list)
    assert len(embedding) == 1536

def test_extract_entities():
    """Test the simple entity extraction."""
    text = "Here are my ideas:\n- An app for cats.\n- A new type of cheese."
    entities = extract_entities(text)
    assert "ideas" in entities
    assert len(entities["ideas"]) == 2
    assert entities["ideas"][0] == "An app for cats."

@pytest.mark.parametrize("source_type", ["journal_entry", "message"])
def test_run_processing_pipeline(mocker, test_user, source_type):
    """
    Test the full processing pipeline orchestration.
    This is an integration test for the pipeline.
    """
    # 1. Mock external services
    mock_generate_embedding = mocker.patch("agent.pipeline.generate_embedding")
    mock_generate_embedding.return_value = [0.2] * 1536
    
    mock_graph_add_idea = mocker.patch("agent.graph_db.GraphDB.add_idea_node")
    mock_graph_link_idea = mocker.patch("agent.graph_db.GraphDB.link_journal_to_idea")

    # 2. Create a source item in the database
    content = "This is a test with an idea:\n- A new social network."
    if source_type == "journal_entry":
        source_id = db.create_journal_entry(test_user["id"], content, {"mood": 5})
    else: # message
        source_id = db.create_conversation_message(test_user["id"], "test_session", "user", content)
    
    # 3. Run the pipeline
    run_processing_pipeline(source_type, source_id)
    
    # 4. Assertions
    # Content is passed as-is to generate_embedding, which handles newline replacement internally

    # Assert embedding was generated
    mock_generate_embedding.assert_called_once_with(content, model="text-embedding-3-small")
    
    # Assert embedding was stored in PostgreSQL
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT vector FROM embeddings WHERE source_type = %s AND source_id = %s;", (source_type, source_id))
        result = cur.fetchone()
        assert result is not None
        assert len(result[0]) == 1536


    
    # Graph DB integration is tested separately in test_graph_db.py
    # Focus here is on embedding storage and pipeline execution

    # Assert processing status is 'complete'
    table_name = "journal_entries" if source_type == "journal_entry" else "conversation_messages"
    with conn.cursor() as cur:
        cur.execute(f"SELECT processing_status FROM {table_name} WHERE id = %s;", (source_id,))
        status = cur.fetchone()[0]
        assert status == "complete"
