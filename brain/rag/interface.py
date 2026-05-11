"""RAG interface — abstract knowledge base integration for Brain.

Defines the contract for future RAG (Retrieval-Augmented Generation) modules.
No implementation in Phase 0-3 — the PRD explicitly defers this.
"""

from abc import ABC, abstractmethod
from typing import Any


class KnowledgeBase(ABC):
    """Abstract knowledge base for retrieving operational context.

    Future implementations:
    - Vector store (Chroma, Milvus)
    - File-based KB (runbooks, docs)
    - API-backed KB (Confluence, Notion)
    """

    @abstractmethod
    async def query(self, question: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Retrieve relevant context for a question.

        Returns a list of dicts with at least "content" and "score" keys.
        Returns empty list when KB is not connected.
        """
        ...

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Check if the knowledge base is reachable.

        Returns {"connected": bool, "error": str | None}.
        """
        ...
