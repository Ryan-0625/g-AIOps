"""LLM adapter abstract interface.

All LLM providers (Ollama, OpenAI, etc.) must implement this interface.
Core Brain logic never imports Ollama-specific code.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class LLMAdapter(ABC):
    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streaming chat. Yields raw response chunks from the provider."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Non-streaming chat (single-shot)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release provider resources (HTTP sessions, etc.)."""
        ...
