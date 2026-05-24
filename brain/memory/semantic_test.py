"""Tests for the Semantic Memory module."""

import pytest
from memory.semantic import SemanticMemory, KnowledgeEntry


@pytest.fixture
def kb():
    return SemanticMemory()


@pytest.mark.asyncio
async def test_query_exact_match(kb):
    result = await kb.query("disk.usage", "usage_pct>90")
    assert result is not None
    assert result.topic == "disk_full"
    assert "cleanup" in result.solution.lower()


@pytest.mark.asyncio
async def test_query_wildcard(kb):
    result = await kb.query("NO_AVAILABLE_WORKER", None)
    assert result is not None
    assert result.topic == "tool_not_found"


@pytest.mark.asyncio
async def test_query_unknown_returns_none(kb):
    result = await kb.query("nonexistent.tool", "SOME_ERROR")
    assert result is None


@pytest.mark.asyncio
async def test_learn_new_knowledge(kb):
    new_entry = KnowledgeEntry(
        topic="custom_test",
        pattern="custom.test:FAILED",
        solution="Restart the custom service",
        confidence=0.5,
        source="learned",
    )
    await kb.learn(new_entry)

    result = await kb.query("custom.test", "FAILED")
    assert result is not None
    assert result.topic == "custom_test"


@pytest.mark.asyncio
async def test_learn_updates_confidence(kb):
    # First learning
    await kb.learn(KnowledgeEntry(
        topic="disk_full", pattern="disk.usage:usage_pct>90",
        solution="Clean up", confidence=0.5, source="learned",
    ))

    result = await kb.query("disk.usage", "usage_pct>90")
    assert result.confidence > 0.5  # Should be increased
    assert result.source == "learned"


@pytest.mark.asyncio
async def test_search(kb):
    results = await kb.search("disk")
    assert len(results) >= 1
    assert any("disk" in r.topic.lower() for r in results)


@pytest.mark.asyncio
async def test_stats(kb):
    stats = kb.stats()
    assert stats["total_entries"] >= 6  # predefined seeds
    assert stats["by_source"]["predefined"] >= 6
