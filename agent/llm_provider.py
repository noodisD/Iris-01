"""
LLM Provider Interface - Model-Agnostic Abstraction

This module defines a clean interface for different LLM providers (OpenAI, Gemini, Claude, etc.).
Each provider handles:
- Message format translation (role names, structure)
- Tool/function calling support
- Streaming and async behavior
- Error handling and retries

Benefits:
- Intelligence class delegates to the active provider
- Adding a new model = implementing one interface
- Model-specific quirks are isolated in provider classes
- Easy to mock providers for testing
- Tests never need to know about OpenAI vs Gemini details
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncIterator
import logging

logger = logging.getLogger(__name__)


class Message:
    """Normalized message representation."""

    def __init__(self, role: str, content: str, tool_calls: Optional[List[Dict]] = None):
        """
        Args:
            role: 'user', 'assistant', or 'system'
            content: The message text
            tool_calls: Optional list of tool calls made by the assistant
        """
        self.role = role
        self.content = content
        self.tool_calls = tool_calls or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to normalized dict format."""
        return {
            'role': self.role,
            'content': self.content,
            'tool_calls': self.tool_calls
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Each provider handles the specifics of communicating with a particular LLM
    (OpenAI, Gemini, Anthropic, etc.). The Intelligence class uses this interface
    without knowing which provider is active.
    """

    @abstractmethod
    def chat(self, messages: List[Message], tools: Optional[List[Dict]] = None,
            temperature: float = 0.7) -> str:
        """Generate a chat response.

        Args:
            messages: Conversation history
            tools: Optional list of tools/functions the model can call
            temperature: Sampling temperature (0-1)

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    async def chat_async(self, messages: List[Message], tools: Optional[List[Dict]] = None,
                        temperature: float = 0.7) -> str:
        """Async version of chat."""
        pass

    @abstractmethod
    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert normalized messages to provider-specific format.

        Each provider has different role names and message structures.
        This method handles that translation.
        """
        pass

    @abstractmethod
    def format_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """Convert normalized tool specs to provider format."""
        pass

    def stream(self, messages: List[Message], tools: Optional[List[Dict]] = None,
              temperature: float = 0.7) -> str:
        """Stream a response token-by-token (if supported by provider)."""
        # Default: fall back to non-streaming chat
        return self.chat(messages, tools, temperature)


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI's GPT models."""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model name (e.g. 'gpt-4', 'gpt-3.5-turbo')
        """
        self.api_key = api_key
        self.model = model
        try:
            from openai import OpenAI, AsyncOpenAI
            self.client = OpenAI(api_key=api_key)
            self.async_client = AsyncOpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai package required for OpenAIProvider")

    def chat(self, messages: List[Message], tools: Optional[List[Dict]] = None,
            temperature: float = 0.7) -> str:
        """Generate response using OpenAI API."""
        formatted_messages = self.format_messages(messages)
        formatted_tools = self.format_tools(tools) if tools else None

        kwargs = {
            'model': self.model,
            'messages': formatted_messages,
            'temperature': temperature,
        }
        if formatted_tools:
            kwargs['tools'] = formatted_tools

        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def chat_async(self, messages: List[Message], tools: Optional[List[Dict]] = None,
                        temperature: float = 0.7) -> str:
        """Async version using OpenAI's async client."""
        formatted_messages = self.format_messages(messages)
        formatted_tools = self.format_tools(tools) if tools else None

        kwargs = {
            'model': self.model,
            'messages': formatted_messages,
            'temperature': temperature,
        }
        if formatted_tools:
            kwargs['tools'] = formatted_tools

        try:
            response = await self.async_client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI async API error: {e}")
            raise

    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """OpenAI uses standard role names: user, assistant, system."""
        result = []
        for msg in messages:
            result.append({
                'role': msg.role,
                'content': msg.content
            })
        return result

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OpenAI expects tools in a specific format."""
        # OpenAI uses "tools" with type "function"
        return [
            {
                'type': 'function',
                'function': tool
            }
            for tool in tools
        ]


class GeminiProvider(LLMProvider):
    """Provider for Google's Gemini models."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):
        """Initialize Gemini provider.

        Args:
            api_key: Google API key
            model: Model name (e.g. 'gemini-1.5-pro', 'gemini-1.0-pro')
        """
        self.api_key = api_key
        self.model = model
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(model)
        except ImportError:
            raise ImportError("google-generativeai package required for GeminiProvider")

    def chat(self, messages: List[Message], tools: Optional[List[Dict]] = None,
            temperature: float = 0.7) -> str:
        """Generate response using Gemini API."""
        formatted_messages = self.format_messages(messages)

        try:
            response = self.client.generate_content(
                formatted_messages,
                generation_config={'temperature': temperature},
                # Note: tool support is limited in Gemini
            )
            return response.text or ""
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise

    async def chat_async(self, messages: List[Message], tools: Optional[List[Dict]] = None,
                        temperature: float = 0.7) -> str:
        """Async version (Gemini has limited async support)."""
        # For now, fall back to sync
        return self.chat(messages, tools, temperature)

    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Gemini uses 'user' and 'model' roles instead of 'assistant'."""
        result = []
        for msg in messages:
            role = 'model' if msg.role == 'assistant' else msg.role
            result.append({
                'role': role,
                'parts': [msg.content]
            })
        return result

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Gemini has limited tool support; return as-is."""
        # Gemini doesn't support tools in the same way OpenAI does
        logger.warning("Gemini has limited tool support")
        return tools


class MockProvider(LLMProvider):
    """Mock provider for testing."""

    def __init__(self, response: str = "Mock response"):
        """Initialize mock provider.

        Args:
            response: Response to return from chat
        """
        self.response = response
        self.call_count = 0
        self.last_messages = None
        self.last_tools = None

    def chat(self, messages: List[Message], tools: Optional[List[Dict]] = None,
            temperature: float = 0.7) -> str:
        """Return mock response."""
        self.call_count += 1
        self.last_messages = messages
        self.last_tools = tools
        return self.response

    async def chat_async(self, messages: List[Message], tools: Optional[List[Dict]] = None,
                        temperature: float = 0.7) -> str:
        """Async mock."""
        return self.chat(messages, tools, temperature)

    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Return messages as-is."""
        return [msg.to_dict() for msg in messages]

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return tools as-is."""
        return tools


class ProviderFactory:
    """Factory for creating LLM providers."""

    _providers = {
        'openai': OpenAIProvider,
        'gemini': GeminiProvider,
        'mock': MockProvider,
    }

    @classmethod
    def register(cls, name: str, provider_class) -> None:
        """Register a new provider."""
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, provider_name: str, **kwargs) -> LLMProvider:
        """Create a provider instance.

        Args:
            provider_name: Name of provider ('openai', 'gemini', 'mock', etc.)
            **kwargs: Arguments to pass to provider constructor

        Returns:
            LLMProvider instance
        """
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")

        return provider_class(**kwargs)
