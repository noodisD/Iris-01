"""
Tests for the Core Orchestrator.
"""

import pytest
from agent.core import PersonalAICompanion

@pytest.fixture
def companion(test_user):
    """Fixture to initialize the PersonalAICompanion for a test user."""
    return PersonalAICompanion(user_id=test_user["id"])

def test_companion_initialization(companion, test_user):
    """Test that the companion initializes correctly."""
    assert companion.user_id == test_user["id"]
    assert companion.memory is not None
    assert companion.journal_entry_service is not None

def test_chat_method(companion, mocker):
    """
    Test the main chat method, mocking external services.
    This is an integration test for the core application logic.
    """
    # 1. Mock the services that are called by chat()
    mock_add_message = mocker.patch("agent.memory.ConversationMemory.add_message")
    mock_get_context = mocker.patch("agent.core.PersonalAICompanion._get_relevant_context")
    mock_get_context.return_value = "Some relevant context from the past."
    mock_llm_chat = mocker.patch("agent.intelligence.Intelligence.chat")
    mock_llm_chat.return_value = "This is the assistant's response."

    user_message = "This is a test message."
    
    # 2. Call the chat method
    response = companion.chat(user_message)
    
    # 3. Assertions
    assert response == "This is the assistant's response."
    
    # Check that memory was updated for both user and assistant
    assert mock_add_message.call_count == 2
    mock_add_message.assert_any_call("user", user_message)
    mock_add_message.assert_any_call("assistant", "This is the assistant's response.")

    # Check that the context retrieval was called
    mock_get_context.assert_called_once_with(user_message)
    
    # Check that the LLM was called with the enhanced prompt
    mock_llm_chat.assert_called_once()
    call_args = mock_llm_chat.call_args
    assert "system_prompt" in call_args.kwargs
    assert "Relevant Long-Term Memory" in call_args.kwargs["system_prompt"]
    assert "Some relevant context" in call_args.kwargs["system_prompt"]

def test_get_relevant_context(companion, mocker):
    """Test the context retrieval sub-process."""
    # Mock the functions/methods called by _get_relevant_context
    mock_generate_embedding = mocker.patch("agent.core.generate_embedding")
    mock_generate_embedding.return_value = [0.3] * 1536
    
    context = companion._get_relevant_context("Some text")\n    \n    mock_generate_embedding.assert_called_once_with("Some text")\n    assert "Similar thoughts from your journal" in context
    assert "Journal Entry ID: journal-123" in context
