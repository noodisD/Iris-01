"""
Tests for the Persistence Engine.
"""

from datetime import datetime

import pytest

from agent.persistence import PersistenceEngine


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
    # Vectors are designed to form clusters (similar to each other)
    vectors = []
    for i in range(10):
        # Create vectors that are similar to each other (should cluster together)
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

    # The important thing is that at least one theme is discovered
    # Different clustering algorithms (DBSCAN vs HDBSCAN) may produce different numbers of clusters
    assert len(new_themes) >= 1, "At least one theme should be discovered"
    assert new_themes[0]["id"] == 50
    assert new_themes[0]["summary"] == "Discovered Theme"
    # The occurrence count depends on how many vectors were clustered together
    assert new_themes[0]["occurrence_count"] > 0, "Should have at least one occurrence"
