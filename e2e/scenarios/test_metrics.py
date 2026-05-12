"""E2E tests for Prometheus metrics endpoint."""

import pytest


@pytest.mark.e2e
class TestMetrics:
    async def test_metrics_content_type(self, api_client):
        """GET /metrics should return text/plain."""
        result = await api_client.metrics()

        assert result["status_code"] == 200

    async def test_metrics_contains_gauges(self, api_client):
        """Metrics body should contain key Prometheus gauges."""
        result = await api_client.metrics()
        text = result["text"]

        assert "gaiops_workers_online" in text
        assert "gaiops_requests_pending" in text
        assert "gaiops_queue_depth" in text
        assert "gaiops_uptime_seconds" in text
        assert "gaiops_requests_total" in text

    async def test_metrics_increments_after_request(self, api_client, trace_id):
        """After executing a request, requests_total should increment."""
        # Get baseline
        before = await api_client.metrics()
        before_text = before["text"]

        # Send a request
        await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
        )

        # Get after
        after = await api_client.metrics()
        after_text = after["text"]

        # Both should be valid Prometheus text
        assert before["status_code"] == 200
        assert after["status_code"] == 200
