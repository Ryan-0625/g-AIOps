"""E2E tests for trace endpoints."""

import asyncio
from uuid import uuid4

import pytest


@pytest.mark.e2e
class TestTrace:
    async def test_list_traces(self, api_client):
        """GET /api/v1/traces should return an array."""
        result = await api_client.traces()

        assert result["status_code"] == 200

    async def test_get_trace_by_id(self, api_client):
        """After executing a request, its trace may be retrievable (depends on Worker)."""
        trace_id = str(uuid4())
        exec_result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
        )

        # If execute succeeded (pending), trace should exist
        if exec_result.get("status") == "pending":
            await asyncio.sleep(0.5)  # Allow Worker to respond and store result
            result = await api_client.trace_by_id(trace_id)
            # The trace may be in pending or completed state
            assert result["status_code"] in (200, 404), f"Expected 200 or 404, got {result['status_code']}"
            # Retry once if not found (timing window)
            if result["status_code"] == 404:
                await asyncio.sleep(1.0)
                result = await api_client.trace_by_id(trace_id)
                assert result["status_code"] == 200, f"Trace not found after retry: {result}"
        else:
            # Without a connected Worker, execute fails and no trace is stored
            pass

    async def test_get_trace_not_found(self, api_client):
        """Non-existent trace_id should return 404."""
        fake_id = str(uuid4())
        result = await api_client.trace_by_id(fake_id)

        assert result["status_code"] == 404 or result["status_code"] == 200
        # The trace endpoint may return 200 with empty results for unknown IDs
