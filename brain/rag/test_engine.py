"""Tests for the RAG engine."""

import pytest
from rag.engine import (
    RAGEngine, MemoryVectorStore, LLMEmbeddingProvider,
    chunk_document, Document,
)


class MockEmbedder(LLMEmbeddingProvider):
    """Mock embedder that returns deterministic vectors."""

    def __init__(self):
        self._cache = {}
        self._cache_hits = 0
        self._cache_misses = 0

    async def embed(self, text: str) -> list[float]:
        # Return a simple deterministic vector based on text length
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()
        return [float(ord(c)) / 255.0 for c in h[:8]]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]

    def cache_stats(self) -> dict[str, int]:
        return {"hits": self._cache_hits, "misses": self._cache_misses}


@pytest.fixture
def embedder():
    return MockEmbedder()


@pytest.fixture
def vector_store():
    return MemoryVectorStore()


@pytest.fixture
def engine(embedder, vector_store):
    return RAGEngine(embedder, vector_store, chunk_size=100, chunk_overlap=20)


@pytest.mark.asyncio
async def test_index_and_query(engine):
    await engine.index_document(
        doc_id="doc1",
        content="High disk usage on root partition. The /var/log directory is consuming 50GB.",
        metadata={"path": "/"},
        source="monitoring",
        tags=["disk", "linux"],
    )
    results = await engine.query("disk usage", top_k=3)
    assert results.total_found > 0
    assert len(results.documents) > 0
    assert results.query == "disk usage"
    assert results.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_index_multiple_documents(engine):
    await engine.index_document("d1", "Disk is full", tags=["disk"])
    await engine.index_document("d2", "CPU is high", tags=["cpu"])
    await engine.index_document("d3", "Memory is low", tags=["memory"])

    results = await engine.query("disk", top_k=2)
    assert results.total_found >= 1


@pytest.mark.asyncio
async def test_query_with_filters(engine):
    await engine.index_document("d1", "Nginx error", source="monitoring", tags=["nginx"])
    await engine.index_document("d2", "Disk error", source="alert", tags=["disk"])

    results = await engine.query("error", top_k=5, filters={"source": "monitoring"})
    assert results.total_found >= 1
    for doc in results.documents:
        assert doc.source == "monitoring"


@pytest.mark.asyncio
async def test_delete_document(engine):
    await engine.index_document("delme", "Content to delete")
    assert await engine.delete_document("delme_chunk_0") is True


@pytest.mark.asyncio
async def test_health(engine):
    health = await engine.health()
    assert health["connected"] is True
    assert "document_count" in health


def test_chunk_document():
    text = " ".join(["word"] * 200)
    chunks = chunk_document(text, max_chunk_size=50, overlap=5)
    assert len(chunks) >= 3  # 200 words / 50 = 4 chunks


def test_chunk_document_small():
    chunks = chunk_document("small text", max_chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0] == "small text"


@pytest.mark.asyncio
async def test_vector_store_search_empty(vector_store):
    results = await vector_store.search([0.1, 0.2, 0.3])
    assert len(results) == 0


@pytest.mark.asyncio
async def test_vector_store_add_and_search(vector_store):
    doc = Document(
        id="test1",
        content="test content",
        embedding=[1.0, 0.0, 0.0, 0.0],
        tags=["test"],
    )
    await vector_store.add(doc)

    results = await vector_store.search([1.0, 0.0, 0.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0].id == "test1"


@pytest.mark.asyncio
async def test_vector_store_filter_by_tags(vector_store):
    await vector_store.add(Document(id="a", content="a", embedding=[1.0, 0.0], tags=["x"]))
    await vector_store.add(Document(id="b", content="b", embedding=[1.0, 0.0], tags=["y"]))

    results = await vector_store.search([1.0, 0.0], top_k=5, filters={"tags": ["x"]})
    assert len(results) == 1
    assert results[0].id == "a"


@pytest.mark.asyncio
async def test_index_fault_record(engine):
    count = await engine.index_fault_record(
        fault_id="fault-001",
        alert={"action": "disk.usage", "severity": "critical"},
        diagnosis="Disk usage at 95%",
        resolution="Cleaned up old logs",
        tags=["disk", "cleanup"],
    )
    assert count > 0
    results = await engine.query("disk usage", top_k=3)
    assert results.total_found > 0
