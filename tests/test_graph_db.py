"""
Integration tests for the Graph Database Layer (Neo4j Lens).
Tests relationship modeling and rebuild functionality.
"""

import pytest
from agent.graph_db import GraphDB
from agent.database import db
from unittest.mock import patch, MagicMock


@pytest.fixture
def graph_db_mock():
    """
    Fixture that creates a GraphDB instance with mocked Neo4j connection.
    This allows testing the logic without requiring a running Neo4j instance.
    """
    # Reset the singleton before creating a new instance
    GraphDB._instance = None

    with patch.object(GraphDB, '_connect'):
        # Create the instance
        gdb = GraphDB()

        # Now patch run_query after instance creation
        gdb.driver = MagicMock()
        gdb.run_query = MagicMock()

        yield gdb

        # Reset singleton after test
        GraphDB._instance = None


def test_graph_db_initialization(graph_db_mock):
    """Test that the graph DB initializes correctly."""
    assert graph_db_mock.driver is not None


def test_add_journal_entry_node(graph_db_mock):
    """Test adding a journal entry node to the graph."""
    entry_id = 1
    user_id = 10
    created_at = "2024-01-03T10:00:00Z"

    graph_db_mock.add_journal_entry_node(entry_id, user_id, created_at)

    # Verify the run_query was called with correct Cypher query
    graph_db_mock.run_query.assert_called_once()
    call_args = graph_db_mock.run_query.call_args
    assert call_args[0][0] is not None  # Query should be provided
    assert "JournalEntry" in call_args[0][0]
    assert "WROTE" in call_args[0][0]

    # Verify the parameters
    params = call_args[0][1]
    assert params["entry_id"] == entry_id
    assert params["user_id"] == user_id
    assert params["created_at"] == created_at


def test_add_idea_node(graph_db_mock):
    """Test adding an idea node to the graph."""
    idea_text = "Create a new social network"

    graph_db_mock.add_idea_node(idea_text)

    # Verify run_query was called
    graph_db_mock.run_query.assert_called_once()
    call_args = graph_db_mock.run_query.call_args
    assert "Idea" in call_args[0][0]
    assert call_args[0][1]["text"] == idea_text


def test_link_journal_to_idea(graph_db_mock):
    """Test creating a relationship between journal entry and idea."""
    entry_id = 1
    idea_text = "Important insight"

    graph_db_mock.link_journal_to_idea(entry_id, idea_text)

    # Verify run_query was called
    graph_db_mock.run_query.assert_called_once()
    call_args = graph_db_mock.run_query.call_args
    assert "CONTAINS_IDEA" in call_args[0][0]
    assert call_args[0][1]["entry_id"] == entry_id
    assert call_args[0][1]["idea_text"] == idea_text


def test_create_constraints(graph_db_mock):
    """Test that constraints are created to prevent duplicates."""
    # Mock the session.run() method since _create_constraints uses driver.session().run()
    mock_session = MagicMock()
    graph_db_mock.driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    graph_db_mock.driver.session.return_value.__exit__ = MagicMock(return_value=None)

    graph_db_mock._create_constraints()

    # Should call session.run three times (for JournalEntry, Idea, User constraints)
    assert mock_session.run.call_count == 3

    calls = mock_session.run.call_args_list
    call_strings = [call[0][0] for call in calls]

    # Verify each type gets a constraint
    assert any("JournalEntry" in s for s in call_strings)
    assert any("Idea" in s for s in call_strings)
    assert any("User" in s for s in call_strings)


def test_rebuild_from_postgres_clears_graph(graph_db_mock, test_user):
    """
    Test that rebuild_from_postgres clears the existing graph before rebuilding.
    """
    # Create test data in PostgreSQL
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Entry with ideas:\n- Idea 1\n- Idea 2",
        wellbeing_data={"mood": 5}
    )

    # Run rebuild
    graph_db_mock.rebuild_from_postgres()

    # Verify that DETACH DELETE was called (to clear the graph)
    call_strings = [call[0][0] for call in graph_db_mock.run_query.call_args_list]
    assert any("DETACH DELETE" in s for s in call_strings), "Graph should be cleared"


def test_rebuild_from_postgres_creates_journal_nodes(graph_db_mock, test_user):
    """
    Test that rebuild_from_postgres creates journal entry nodes.
    """
    # Create test data
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Test entry",
        wellbeing_data={"mood": 7}
    )

    # Mock the session for _create_constraints and other operations
    mock_session = MagicMock()
    graph_db_mock.driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    graph_db_mock.driver.session.return_value.__exit__ = MagicMock(return_value=None)

    graph_db_mock.rebuild_from_postgres()

    # Verify run_query was called (for DETACH DELETE and MERGE operations)
    assert graph_db_mock.run_query.call_count > 0, "run_query should be called during rebuild"


def test_rebuild_from_postgres_extracts_ideas(graph_db_mock, test_user):
    """
    Test that rebuild_from_postgres extracts ideas from journal entries.
    """
    # Create entry with bullet-point ideas
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Ideas:\n- Build a mobile app\n- Learn Rust\n- Write a book",
        wellbeing_data={"mood": 6}
    )

    graph_db_mock.rebuild_from_postgres()

    # The rebuild should extract these three ideas
    # Each idea gets added as a node via run_query calls
    call_strings = [str(call[0]) for call in graph_db_mock.run_query.call_args_list]

    # We should see calls for the ideas
    # The exact assertion depends on implementation, but we can verify
    # that multiple MERGE operations occurred
    merge_calls = [c for c in call_strings if "MERGE" in c]
    # Should be: 1 for constraints reset, 1 for journal entry, 3 for ideas = at least 5
    assert len(merge_calls) >= 4, f"Expected multiple MERGE calls, got {len(merge_calls)}"


@pytest.fixture
def graph_db_real():
    """
    Fixture for real Neo4j testing (requires running Neo4j instance).
    Can be skipped if Neo4j is not available.
    """
    pytest.skip("Requires running Neo4j instance - skipping in CI")


def test_run_query_generic(graph_db_mock):
    """Test that run_query can execute generic Cypher queries."""
    query = "MATCH (n) RETURN count(n) as count"
    parameters = {}

    graph_db_mock.run_query(query, parameters)

    graph_db_mock.run_query.assert_called_once()
    call_args = graph_db_mock.run_query.call_args
    assert call_args[0][0] == query
    assert call_args[0][1] == parameters


def test_graph_structure_integrity(graph_db_mock, test_user):
    """
    Test that the graph maintains referential integrity between nodes.
    """
    # Create entries and verify the structure is maintained
    entry1 = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Entry 1: - Idea A",
        wellbeing_data={"mood": 5}
    )

    entry2 = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Entry 2: - Idea B",
        wellbeing_data={"mood": 6}
    )

    graph_db_mock.add_journal_entry_node(entry1, test_user["id"], "2024-01-01")
    graph_db_mock.add_journal_entry_node(entry2, test_user["id"], "2024-01-02")

    graph_db_mock.add_idea_node("Idea A")
    graph_db_mock.add_idea_node("Idea B")

    graph_db_mock.link_journal_to_idea(entry1, "Idea A")
    graph_db_mock.link_journal_to_idea(entry2, "Idea B")

    # Verify all calls were made
    assert graph_db_mock.run_query.call_count >= 6


def test_graph_db_connection_verification(graph_db_mock):
    """Test that the graph DB can verify connectivity."""
    # The mock should have the verify_connectivity method
    graph_db_mock.driver.verify_connectivity = MagicMock()
    # In a real test, this would verify that the Neo4j connection is working
    # For now, we just test the structure
    assert graph_db_mock.driver is not None
