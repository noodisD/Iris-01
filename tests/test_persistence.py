"""
Tests for the Persistence Engine.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from agent.persistence import PersistenceEngine
import numpy as np

@pytest.fixture
def engine(test_user):
    return PersistenceEngine(test_user["id"])

def test_check_persistence_match(engine, mocker):
    """Test that check_persistence correctly matches an existing theme."""
    # Mock themes
    test_centroid = [0.1] * 1536
    mock_themes = [
        {
            "id": 1,
            "centroid_embedding": test_centroid,
            "occurrence_count": 1
        }
    ]
    mocker.patch("agent.database.db.get_themes", return_value=mock_themes)
    
    # Mock update methods
    mock_add_occ = mocker.patch("agent.database.db.add_theme_occurrence")
    mock_update_stats = mocker.patch("agent.database.db.update_theme_stats")
    
    # Input embedding (identical to centroid)
    embedding = [0.1] * 1536
    source_type = "journal_entry"
    source_id = 100
    content = "Recurring thought content"
    occurred_at = datetime.now()
    
    matched_id = engine.check_persistence(embedding, source_type, source_id, content, occurred_at)
    
    assert matched_id == 1
    mock_add_occ.assert_called_once()
    mock_update_stats.assert_called_once_with(1, occurred_at.isoformat())

def test_check_persistence_no_match(engine, mocker):
    """Test that check_persistence returns None when no theme matches."""
    # Mock themes with a very different direction centroid
    test_centroid = [1.0] + [0.0] * 1535
    mock_themes = [
        {
            "id": 1,
            "centroid_embedding": test_centroid,
            "occurrence_count": 1
        }
    ]
    mocker.patch("agent.database.db.get_themes", return_value=mock_themes)
    
    # Mock update methods
    mock_add_occ = mocker.patch("agent.database.db.add_theme_occurrence")
    
    # Input embedding (orthogonal to centroid)
    embedding = [0.0, 1.0] + [0.0] * 1534
    
    matched_id = engine.check_persistence(embedding, "journal_entry", 100, "content", datetime.now())
    
    assert matched_id is None
    mock_add_occ.assert_not_called()

def test_discover_themes(engine, mocker):
    """Test theme discovery from unassigned embeddings."""
    # Mock unassigned embeddings
    # HDBSCAN needs more points to be stable
    vectors = []
    for i in range(10):
        v = [1.0, i * 0.001] + [0.0] * 1534
        vectors.append(v)
    
    unassigned = [
        {"source_type": "journal_entry", "source_id": i, "vector": v, "created_at": "2024-01-01T10:00:00Z"}
        for i, v in enumerate(vectors)
    ]
    mocker.patch("agent.database.db.get_unassigned_embeddings", return_value=unassigned)
    
    # Mock summary generation to avoid LLM call
    mocker.patch.object(engine, "_generate_theme_summary", return_value="Discovered Theme")
    
    # Mock database creation
    mocker.patch("agent.database.db.create_theme", return_value=50)
    mocker.patch("agent.database.db.add_theme_occurrence")
    mocker.patch("agent.database.db.get_journal_entry_content", return_value="Sample content")
    
    # Run discovery
    new_themes = engine.discover_themes()
    
    assert len(new_themes) == 1
    assert new_themes[0]["id"] == 50
    assert new_themes[0]["summary"] == "Discovered Theme"
    assert new_themes[0]["occurrence_count"] == 3

def test_format_for_context(engine, mocker):
    """Test formatting themes for LLM context."""
    mock_themes = [
        {
            "id": 1,
            "summary": "Theme A",
            "occurrence_count": 5,
            "first_seen_at": "2024-01-01T00:00:00Z",
            "last_seen_at": "2024-01-10T00:00:00Z"
        },
        {
            "id": 2,
            "summary": "Theme B",
            "occurrence_count": 2,
            "first_seen_at": "2024-01-05T00:00:00Z",
            "last_seen_at": "2024-01-06T00:00:00Z"
        }
    ]
    mocker.patch.object(engine, "get_persistent_themes", return_value=mock_themes)
    
    context = engine.format_for_context()
    
    assert "# What Keeps Coming Back:" in context
    assert 'Theme A" (5 times, last: 2024-01-10)' in context
    assert 'Theme B" (2 times, last: 2024-01-06)' in context
