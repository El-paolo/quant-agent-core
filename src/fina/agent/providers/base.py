"""
LLM provider protocol — the contract every provider must implement.

Using typing.Protocol (structural subtyping) means providers don't need to
inherit from a base class. Any object with a matching chat() signature
satisfies the contract automatically.

To add a new provider:
  1. Create providers/<name>.py implementing LLMProvider
  2. Add an elif branch in summarizer.get_provider()
  3. Add provider settings fields to core/config.py
  No other files need to change.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract for an LLM chat provider."""

    def chat(self, prompt: str) -> str:
        """
        Send a single user prompt and return the model's text response.

        Args:
            prompt: The user message to send.

        Returns:
            The model's text response as a plain string.

        Raises:
            FetcherError: On network errors or unexpected API responses.
        """
        ...

    def is_available(self) -> bool:
        """
        Return True if the provider is reachable and ready.

        Used for health checks and graceful fallback. Should never raise.
        """
        ...
