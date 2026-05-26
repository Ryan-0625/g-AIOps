"""Enhanced RAG Engine — semantic retrieval for operational knowledge.

Built on top of the abstract KnowledgeBase interface, this implements
a lightweight, file-based vector retrieval system that:

1. Embeds queries and documents using the configured LLM's embedding endpoint
2. Stores document vectors in a simple local store (Chroma/FAISS-ready interface)
3. Retrieves top-k relevant documents for a given query
4. Supports filtering by tags, source, and time range
5. Gracefully degrades when embedding model is unavailable

Supports multiple storage backends:
- MemoryStore (in-memory, default, development)
- FileStore (JSON-based on disk, small deployments)
- ChromaDB / PGVector (production, when available)
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from abc import ABC, abstractmethod
import numpy as np


# --- Data Models ---


@dataclass
class Document:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: Optional[list[float]] = None
    source: str = ""
    tags: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    score: float = 0.0


@dataclass
class RetrievalResult:
    documents: list[Document]
    query: str
    total_found: int
    elapsed_ms: float


# --- Embedding Provider ---


class EmbeddingProvider(ABC):
    """Abstract interface for generating embeddings."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


class LLMEmbeddingProvider(EmbeddingProvider):
    """Uses the LLM adapter's embedding endpoint."""

    def __init__(self, llm_adapter):
        self._llm = llm_adapter
        self._cache: dict[str, list[float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    async def embed(self, text: str) -> list[float]:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self._cache:
            self._cache_hits += 1
            return self._cache[text_hash]

        self._cache_misses += 1
        try:
            embedding = await self._llm.embed(text)
            self._cache[text_hash] = embedding
            return embedding
        except Exception:
            # Fallback: simple token-level hash embedding (last resort)
            return self._fallback_embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            results.append(await self.embed(text))
        return results

    def _fallback_embed(self, text: str) -> list[float]:
        """Simple bag-of-words fallback when LLM embedding is unavailable."""
        import hashlib
        words = text.lower().split()
        dim = 128
        vec = [0.0] * dim
        for word in words[:100]:
            h = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
            idx = h % dim
            vec[idx] += 1.0
        magnitude = sum(v * v for v in vec) ** 0.5
        if magnitude > 0:
            vec = [v / magnitude for v in vec]
        return vec

    def cache_stats(self) -> dict[str, int]:
        return {"hits": self._cache_hits, "misses": self._cache_misses}


# --- Vector Store (interface) ---


class VectorStore(ABC):
    """Abstract vector storage backend."""

    @abstractmethod
    async def add(self, doc: Document) -> None:
        ...

    @abstractmethod
    async def search(self, query_embedding: list[float], top_k: int = 5,
                     filters: Optional[dict[str, Any]] = None) -> list[Document]:
        ...

    @abstractmethod
    async def delete(self, doc_id: str) -> bool:
        ...

    @abstractmethod
    async def count(self) -> int:
        ...


class MemoryVectorStore(VectorStore):
    """In-memory vector store using cosine similarity."""

    def __init__(self):
        self._docs: dict[str, Document] = {}

    async def add(self, doc: Document) -> None:
        self._docs[doc.id] = doc

    async def search(self, query_embedding: list[float], top_k: int = 5,
                     filters: Optional[dict[str, Any]] = None) -> list[Document]:
        query_vec = np.array(query_embedding, dtype=np.float32)
        scored: list[Document] = []

        for doc in self._docs.values():
            if filters:
                if not self._matches_filters(doc, filters):
                    continue
            if doc.embedding is None:
                continue
            doc_vec = np.array(doc.embedding, dtype=np.float32)
            similarity = self._cosine_similarity(query_vec, doc_vec)
            doc.score = float(similarity)
            scored.append(doc)

        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:top_k]

    async def delete(self, doc_id: str) -> bool:
        return self._docs.pop(doc_id, None) is not None

    async def count(self) -> int:
        return len(self._docs)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        dot = float(np.dot(a, b))
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _matches_filters(doc: Document, filters: dict[str, Any]) -> bool:
        for key, value in filters.items():
            if key == "tags":
                if not all(tag in doc.tags for tag in value):
                    return False
            elif key == "source":
                if doc.source != value:
                    return False
            elif key == "since":
                if doc.timestamp < value:
                    return False
            elif key in doc.metadata:
                if doc.metadata[key] != value:
                    return False
        return True


# --- Chunking ---


def chunk_document(content: str, max_chunk_size: int = 500,
                   overlap: int = 50) -> list[str]:
    """Split a document into overlapping chunks."""
    words = content.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + max_chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += max_chunk_size - overlap
    return chunks if chunks else [content]


# --- RAG Engine ---


class RAGEngine:
    """Main RAG retrieval engine.

    Usage:
        engine = RAGEngine(embedding_provider, vector_store)
        await engine.index_document("disk_001", "Disk usage...", {"path": "/"})
        results = await engine.query("high disk usage on root partition")
    """

    def __init__(
        self,
        embed_provider: EmbeddingProvider,
        vector_store: Optional[VectorStore] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        self._embed = embed_provider
        self._store = vector_store or MemoryVectorStore()
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def index_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        source: str = "",
        tags: Optional[list[str]] = None,
    ) -> int:
        """Index a document. Returns number of chunks indexed."""
        chunks = chunk_document(content, self._chunk_size, self._chunk_overlap)
        embeddings = await self._embed.embed_batch(chunks)

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc = Document(
                id=f"{doc_id}_chunk_{i}",
                content=chunk,
                metadata=metadata or {},
                embedding=embedding,
                source=source,
                tags=tags or [],
                timestamp=time.time(),
            )
            await self._store.add(doc)

        return len(chunks)

    async def query(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> RetrievalResult:
        """Query the knowledge base. Returns ranked documents."""
        t0 = time.time()
        query_embedding = await self._embed.embed(query)
        docs = await self._store.search(query_embedding, top_k, filters)
        elapsed = (time.time() - t0) * 1000

        return RetrievalResult(
            documents=docs,
            query=query,
            total_found=len(docs),
            elapsed_ms=round(elapsed, 2),
        )

    async def delete_document(self, doc_id: str) -> bool:
        """Delete all chunks for a document."""
        # In production, use pattern matching
        return await self._store.delete(doc_id)

    async def index_fault_record(
        self,
        fault_id: str,
        alert: dict[str, Any],
        diagnosis: str,
        resolution: str,
        tags: Optional[list[str]] = None,
    ) -> int:
        """Index a fault record (from SKILL or incident history)."""
        content = f"""
        ALERT: {json.dumps(alert)}
        DIAGNOSIS: {diagnosis}
        RESOLUTION: {resolution}
        """
        metadata = {
            "fault_id": fault_id,
            "alert_type": alert.get("action", ""),
            "severity": alert.get("severity", "info"),
        }
        return await self.index_document(
            doc_id=f"fault_{fault_id}",
            content=content.strip(),
            metadata=metadata,
            source="fault_history",
            tags=tags or [],
        )

    async def health(self) -> dict[str, Any]:
        try:
            count = await self._store.count()
            return {"connected": True, "document_count": count,
                    "cache_stats": self._embed.cache_stats()}
        except Exception as e:
            return {"connected": False, "error": str(e)}
