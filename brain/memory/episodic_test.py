"""Tests for the Episodic Memory module."""

import pytest
from memory.episodic import EpisodicMemory, Episode


@pytest.fixture
def memory():
    return EpisodicMemory(max_episodes=10)


@pytest.mark.asyncio
async def test_store_and_retrieve(memory):
    episode = Episode(
        trace_id="t1",
        context_hash="abc",
        action="ping.icmp",
        params={"target": "localhost"},
        status="success",
        error_code=None,
        error_message=None,
        summary="Ping successful",
        duration_ms=100,
    )
    await memory.store(episode)

    results = await memory.retrieve_similar(action="ping.icmp")
    assert len(results) == 1
    assert results[0].trace_id == "t1"
    assert results[0].status == "success"


@pytest.mark.asyncio
async def test_retrieve_by_error_code(memory):
    for i in range(3):
        await memory.store(Episode(
            trace_id=f"t{i}",
            context_hash="abc",
            action="disk.usage",
            params={},
            status="failure" if i == 0 else "success",
            error_code="DISK_READ_ERROR" if i == 0 else None,
            error_message="Failed" if i == 0 else None,
            summary=f"Test {i}",
            duration_ms=50,
        ))

    results = await memory.retrieve_similar(action="disk.usage", error_code="DISK_READ_ERROR")
    assert len(results) == 1
    assert results[0].error_code == "DISK_READ_ERROR"


@pytest.mark.asyncio
async def test_max_episodes_eviction(memory):
    for i in range(15):
        await memory.store(Episode(
            trace_id=f"t{i}",
            context_hash=f"ctx{i}",
            action="ping.icmp",
            params={},
            status="success",
            error_code=None,
            error_message=None,
            summary=f"Test {i}",
            duration_ms=10,
        ))

    assert len(memory.episodes) == 10  # max_episodes
    # Oldest entries should be evicted
    trace_ids = [e.trace_id for e in memory.episodes]
    assert "t0" not in trace_ids
    assert "t14" in trace_ids


@pytest.mark.asyncio
async def test_retrieve_by_context(memory):
    await memory.store(Episode(
        trace_id="t1", context_hash="ctx_a", action="ping.icmp",
        params={}, status="success", error_code=None,
        error_message=None, summary="OK", duration_ms=10,
    ))
    await memory.store(Episode(
        trace_id="t2", context_hash="ctx_a", action="disk.usage",
        params={}, status="success", error_code=None,
        error_message=None, summary="OK", duration_ms=10,
    ))
    await memory.store(Episode(
        trace_id="t3", context_hash="ctx_b", action="ping.icmp",
        params={}, status="success", error_code=None,
        error_message=None, summary="OK", duration_ms=10,
    ))

    results = await memory.retrieve_by_context("ctx_a")
    assert len(results) == 2
    assert results[0].trace_id == "t1"
    assert results[1].trace_id == "t2"


@pytest.mark.asyncio
async def test_stats(memory):
    await memory.store(Episode(
        trace_id="t1", context_hash="a", action="ping.icmp",
        params={}, status="success", error_code=None,
        error_message=None, summary="OK", duration_ms=10,
    ))
    await memory.store(Episode(
        trace_id="t2", context_hash="b", action="disk.usage",
        params={}, status="failure", error_code="ERROR",
        error_message="Fail", summary="FAIL", duration_ms=10,
    ))

    stats = memory.stats()
    assert stats["total_episodes"] == 2
    assert stats["success_count"] == 1
    assert stats["failure_count"] == 1
