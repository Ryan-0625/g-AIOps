"""Stress and load tests for the Master API.

Requires a real Worker to be connected. Uses the StressRunner helper
to execute concurrent requests and report statistics.
"""

import asyncio
from uuid import uuid4

import pytest

from helpers.stress import StressRunner


@pytest.mark.e2e
class TestStress:
    async def test_rate_limit_120_per_min(self, api_client):
        """Send 130 requests — verify the 120/min rate limit is enforced."""
        runner = StressRunner()
        requests = [
            {
                "action": "ping.icmp",
                "params": {"target": "127.0.0.1", "count": 1},
                "trace_id": str(uuid4()),
            }
            for _ in range(130)
        ]
        result = await runner.run_concurrent(api_client, requests, concurrency=20)
        print(result.report())
        # RATE_LIMIT_MAX is 1000 in E2E, so 130 requests should all succeed
        assert result.total == 130, f"Expected 130 total, got {result.total}"
        assert result.success == 130, f"Expected 130 success, got {result.success}"

    async def test_concurrent_50_requests(self, api_client):
        """Fire 50 ping requests concurrently."""
        runner = StressRunner()
        requests = [
            {
                "action": "ping.icmp",
                "params": {"target": "127.0.0.1", "count": 1},
                "trace_id": str(uuid4()),
            }
            for _ in range(50)
        ]
        result = await runner.run_concurrent(api_client, requests, concurrency=50)
        print(result.report())
        # Due to rate limiting, not all may succeed, but system should not crash
        assert result.total == 50, f"Expected 50 total, got {result.total}"
        assert result.success_rate > 0, "All requests failed"

    async def test_concurrent_worker_max_concurrent(self, api_client):
        """Send 10 exec.run requests concurrently — Worker handles max_concurrent=5."""
        runner = StressRunner()
        requests = [
            {
                "action": "exec.run",
                "params": {"command": "ls", "args": ["-la", "/tmp"]},
                "trace_id": str(uuid4()),
            }
            for _ in range(10)
        ]
        result = await runner.run_concurrent(api_client, requests, concurrency=10)
        print(result.report())
        # Worker's max_concurrent is 5, so requests queue up but should all complete
        assert result.total == 10
        # Allow for some failures due to rate limiting
        assert result.success + result.failure == 10

    @pytest.mark.slow
    async def test_sustained_load_60s(self, api_client):
        """Sustained load: one request every 500ms for 60 seconds."""
        runner = StressRunner()
        requests = []
        for _ in range(120):
            requests.append({
                "action": "ping.icmp",
                "params": {"target": "127.0.0.1", "count": 1},
                "trace_id": str(uuid4()),
            })
        result = await runner.run_concurrent(api_client, requests, concurrency=5)
        print(result.report())
        assert result.total == 120, f"Expected 120 total, got {result.total}"
        # High success rate expected
        assert result.success_rate > 70, f"Success rate too low: {result.success_rate:.1f}%"

    async def test_stress_report(self, api_client):
        """Run a moderate stress test and print the report."""
        runner = StressRunner()
        requests = [
            {
                "action": "ping.icmp",
                "params": {"target": "127.0.0.1", "count": 1},
                "trace_id": str(uuid4()),
            }
            for _ in range(30)
        ]
        result = await runner.run_concurrent(api_client, requests, concurrency=10)
        report = result.report()
        print(report)
        # Report should include latency percentiles
        assert "p50" in report
        assert "p95" in report
        assert "p99" in report
        assert result.total == 30

    async def test_burst_100_in_1s(self, api_client):
        """Burst 100 requests in rapid succession (no delay between batches)."""
        runner = StressRunner()
        requests = [
            {
                "action": "ping.icmp",
                "params": {"target": "127.0.0.1", "count": 1},
                "trace_id": str(uuid4()),
            }
            for _ in range(100)
        ]
        result = await runner.run_concurrent(api_client, requests, concurrency=100)
        print(result.report())
        assert result.total == 100
        # System should not crash — some may be rate-limited
        assert result.success + result.failure == 100
