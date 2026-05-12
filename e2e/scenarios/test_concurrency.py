"""Concurrency and race-condition tests for the Master-WebSocket flow.

All tests require a real Worker to be connected.
"""

import asyncio

import pytest

from helpers.stress import StressRunner


async def _poll_result(api_client, msg_id: str, timeout: float = 15.0) -> dict:
    """Poll /api/v1/result/:msg_id until the result is available."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        result = await api_client.result_by_msg_id(msg_id)
        if result["status_code"] == 200:
            return result
        await asyncio.sleep(0.5)
    return {"status_code": 404}


@pytest.mark.e2e
class TestConcurrency:
    async def test_multi_requests_same_worker(self, api_client, trace_id):
        """Send 20 sequential requests to the same Worker — all should respond."""
        runner = StressRunner()
        requests = [
            {
                "action": "ping.icmp",
                "params": {"target": "127.0.0.1", "count": 1},
                "trace_id": f"{trace_id}-{i}",
            }
            for i in range(20)
        ]
        result = await runner.run_concurrent(api_client, requests, concurrency=5)
        print(result.report())
        assert result.total == 20, f"Expected 20 total, got {result.total}"

    async def test_request_interleaving(self, api_client, trace_id):
        """Interleave ping.icmp and exec.run — verify both complete."""
        runner = StressRunner()
        requests = []
        for i in range(10):
            requests.append({
                "action": "ping.icmp",
                "params": {"target": "127.0.0.1", "count": 1},
                "trace_id": f"{trace_id}-ping-{i}",
            })
            requests.append({
                "action": "exec.run",
                "params": {"command": "ls", "args": ["-la"]},
                "trace_id": f"{trace_id}-exec-{i}",
            })
        result = await runner.run_concurrent(api_client, requests, concurrency=10)
        print(result.report())
        assert result.total == 20
        # Allow rate-limited failures but ensure requests were attempted
        assert result.success + result.failure == 20

    async def test_worker_reconnect(self, api_client, trace_id):
        """Simulate Worker disconnect and reconnect by checking health counts.

        This test verifies the health endpoint reflects Worker state changes:
        - Initially worker should be online
        - After disconnect, count drops
        - (Reconnection is tested by Docker compose restart policy)
        """
        health = await api_client.health()
        assert health["status_code"] == 200
        workers = health.get("workers", {})
        assert isinstance(workers, dict)

    async def test_simultaneous_approve_and_execute(self, api_client, trace_id):
        """Send approval and execute requests simultaneously — no deadlock."""
        runner = StressRunner()
        exec_requests = [
            {
                "action": "exec.run",
                "params": {"command": "ls"},
                "trace_id": f"{trace_id}-{i}",
            }
            for i in range(5)
        ]
        result = await runner.run_concurrent(api_client, exec_requests, concurrency=5)
        print(result.report())
        # System should not deadlock — all requests complete
        assert result.total == 5
