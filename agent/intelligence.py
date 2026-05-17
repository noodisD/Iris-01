"""
Intelligence layer - Multi-model support (Gemini 2.5 Flash, OpenAI)
"""

import warnings
import os
from openai import AsyncOpenAI, OpenAI
from typing import Optional, List, Dict, Any
from .config import settings
from .llm_provider import LLMProvider, OpenAIProvider, GeminiProvider, Message

try:
    # Suppress deprecation warning for google.generativeai (still works, just deprecated)
    warnings.filterwarnings("ignore", category=FutureWarning)
    import google.generativeai as genai
    warnings.resetwarnings()
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class Intelligence:
    """Multi-model wrapper: OpenAI (primary), Gemini (fallback)"""

    def __init__(self, api_key: Optional[str] = None, model: str = None, use_gemini: bool = False):
        """Initialize intelligence layer with multi-model support"""
        self.use_gemini = use_gemini
        self.gemini_client = None
        self.openai_client = None
        self.model = model or settings.OPENAI_MODEL

        # LLM Provider (abstraction for pluggable model support)
        self.provider: Optional[LLMProvider] = None

        # Initialize OpenAI first (primary)
        openai_key = api_key or settings.OPENAI_API_KEY

        if openai_key and openai_key != "your_openai_api_key_here":
            try:
                self.openai_client = OpenAI(api_key=openai_key)
                self.async_client = AsyncOpenAI(api_key=openai_key)

                # Initialize OpenAI provider
                self.provider = OpenAIProvider(api_key=openai_key, model=self.model)

                self.use_gemini = False
            except Exception as e:
                print(f"⚠️  OpenAI initialization failed: {e}")

        # Initialize Gemini as fallback if requested and available
        if use_gemini and GEMINI_AVAILABLE:
            gemini_key = api_key or os.getenv("GEMINI_API_KEY")
            if gemini_key and gemini_key != "your_gemini_api_key_here":
                try:
                    genai.configure(api_key=gemini_key)
                    self.gemini_client = genai.GenerativeModel(
                        model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
                    )

                    # Initialize Gemini provider
                    self.provider = GeminiProvider(
                        api_key=gemini_key,
                        model=os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
                    )

                    self.use_gemini = True
                except Exception as e:
                    print(f"⚠️  Gemini initialization failed: {e}. Using OpenAI instead.")
                    self.use_gemini = False
            else:
                if use_gemini:
                    print("⚠️  Gemini API key not set. Using OpenAI.")
                self.use_gemini = False

        if not self.openai_client and not self.gemini_client:
            raise ValueError(
                "No API keys configured. Set OPENAI_API_KEY or GEMINI_API_KEY in .env"
            )

    def set_model(self, model: str) -> None:
        """Switch the active model

        Args:
            model: Model name (e.g., "gpt-4o-mini", "gpt-4o")
        """
        self.model = model
        # Update provider model if available
        if self.provider:
            self.provider.model = model

    def chat_with_provider(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
    ) -> str:
        """Chat using the provider interface (model-agnostic).

        This method routes through the LLMProvider abstraction,
        allowing easy switching between models without code changes.

        Args:
            messages: Conversation history
            system_prompt: System prompt
            tools: Optional tool definitions
            temperature: Sampling temperature

        Returns:
            Response text
        """
        if not self.provider:
            return "Error: No LLM provider available"

        try:
            # Convert messages to provider format
            provider_messages = [Message(role="system", content=system_prompt)]
            for msg in messages:
                provider_messages.append(Message(role=msg["role"], content=msg["content"]))

            # Call through provider
            return self.provider.chat(
                messages=provider_messages,
                tools=tools,
                temperature=temperature
            )
        except Exception as e:
            return f"Error calling provider: {str(e)}"

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        model: Optional[str] = None,
    ) -> str:
        """Unified chat interface - routes to OpenAI or Gemini with automatic fallback

        Args:
            messages: List of {role, content} dicts
            system_prompt: System message defining behavior
            tools: Optional tool definitions for function calling
            temperature: Creativity level (0-1)
            max_tokens: Max response length
            model: Optional model override

        Returns:
            Response text from the model
        """
        try:
            if self.openai_client:
                return self._chat_openai(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools
                )
            elif self.use_gemini and self.gemini_client:
                response = self._chat_gemini(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                # Check if response is an error string
                if response.startswith("Gemini API error:"):
                    return response
                return response
            else:
                return "Error: No API client available"

        except Exception as e:
            return f"Error calling API: {str(e)}"

    def _chat_gemini(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """Call Gemini 2.5 Flash API with proper system prompt support

        Args:
            messages: Conversation messages
            system_prompt: System context (passed separately, not concatenated)
            temperature: Sampling temperature
            max_tokens: Response length limit

        Returns:
            Response text
        """
        try:
            # Format messages for Gemini
            conversation = []
            for msg in messages:
                if msg["role"] == "user":
                    conversation.append({"role": "user", "parts": [msg["content"]]})
                elif msg["role"] == "assistant":
                    conversation.append({"role": "model", "parts": [msg["content"]]})

            # Create generation config
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
                "top_k": 40,
            }

            # Use system_instruction parameter (Gemini 2.5 Pro supports this natively)
            # This avoids concatenating the system prompt with user message, which was triggering safety filters
            gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
            client_with_system = genai.GenerativeModel(
                model_name=gemini_model,
                system_instruction=system_prompt  # Pass system prompt separately
            )

            # Start chat session with full conversation history
            chat_session = client_with_system.start_chat(history=conversation[:-1] if len(conversation) > 1 else [])

            # Get the last user message
            if conversation:
                last_message = conversation[-1]["parts"][0]
            else:
                return "Error: No user message provided"

            # Send message without concatenating system prompt
            response = chat_session.send_message(
                last_message,
                generation_config=generation_config
            )

            # Handle response safely
            try:
                # Try direct .text accessor
                return response.text
            except (ValueError, AttributeError, RuntimeError) as e:
                # If .text fails, try to get from candidates
                if hasattr(response, 'candidates') and response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts:
                        parts = candidate.content.parts
                        if parts and hasattr(parts[0], 'text'):
                            return parts[0].text
                # If still no content, might be a safety block
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'finish_reason'):
                        finish_reason = candidate.finish_reason
                        return f"Gemini API error: Response blocked (finish_reason: {finish_reason})"
                return f"Gemini API error: {str(e)}"

        except Exception as e:
            return f"Gemini API error: {str(e)}"

    def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Call OpenAI API (fallback)

        Args:
            messages: Conversation messages
            system_prompt: System context
            temperature: Sampling temperature
            max_tokens: Response length limit
            tools: Optional function calling tools

        Returns:
            Response text
        """
        try:
            # Prepare messages with system prompt
            full_messages = [
                {"role": "system", "content": system_prompt},
                *messages
            ]

            # Prepare request kwargs
            kwargs = {
                "model": self.model,
                "messages": full_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # Add tools if provided
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            # Call API
            response = self.openai_client.chat.completions.create(**kwargs)

            # Extract response
            if response.choices[0].message.content:
                return response.choices[0].message.content
            else:
                return "[No response content]"

        except Exception as e:
            return f"OpenAI API error: {str(e)}"

    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Asynchronous chat with optional tool calling

        Args:
            messages: List of {role, content} dicts
            system_prompt: System message defining behavior
            tools: Optional list of tool definitions for function calling
            temperature: Creativity level (0-1)
            max_tokens: Max response length

        Returns:
            Response text from the model
        """
        try:
            # Prepare messages with system prompt
            full_messages = [
                {"role": "system", "content": system_prompt},
                *messages
            ]

            # Prepare request kwargs
            kwargs = {
                "model": self.model,
                "messages": full_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # Add tools if provided
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            # Call API
            response = await self.async_client.chat.completions.create(**kwargs)

            # Extract response
            if response.choices[0].message.content:
                return response.choices[0].message.content
            else:
                return "[No response content]"

        except Exception as e:
            return f"Error calling API: {str(e)}"

    def estimate_cost(self, messages: List[Dict[str, str]]) -> Dict[str, float]:
        """Rough estimate of API cost

        GPT-4o-mini: $0.15 per 1M input tokens, $0.60 per 1M output tokens
        Average: ~1.3 tokens per word

        Returns:
            Dict with estimated_input_cost and estimated_output_cost
        """
        # Count total words
        total_words = sum(len(msg.get("content", "").split()) for msg in messages)
        input_tokens = int(total_words * 1.3)
        output_tokens = 2000  # max_tokens assumption

        input_cost = (input_tokens / 1_000_000) * 0.15
        output_cost = (output_tokens / 1_000_000) * 0.60

        return {
            "estimated_input_cost": input_cost,
            "estimated_output_cost": output_cost,
            "total_estimated_cost": input_cost + output_cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
