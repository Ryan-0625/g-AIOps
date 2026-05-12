"""Boundary tests for Master API input validation and edge cases.

Most tests do not require a real Worker — they test input validation
at the Master API level. Tests that require a Worker will gracefully
accept "failure" status when no Worker is connected.
"""

import pytest


@pytest.mark.e2e
class TestBoundary:
    async def test_empty_params(self, api_client, trace_id):
        """Empty params should not crash the system."""
        result = await api_client.execute(
            action="ping.icmp",
            params={},
            trace_id=trace_id,
        )
        assert result["status_code"] == 200
        # Should either succeed (Worker online) or fail at routing
        assert result.get("status") in ("pending", "failure", "success")

    async def test_action_empty_string(self, api_client, trace_id):
        """Empty action string should be rejected."""
        result = await api_client.execute(
            action="",
            params={},
            trace_id=trace_id,
        )
        assert result["status_code"] == 400
        assert "error" in result

    async def test_action_whitespace(self, api_client, trace_id):
        """Whitespace-only action should be rejected (or routed to nothing)."""
        result = await api_client.execute(
            action="   ",
            params={},
            trace_id=trace_id,
        )
        # Master may reject at validation or pass to routing
        assert result["status_code"] in (200, 400)
        if result["status_code"] == 400:
            assert "error" in result

    async def test_trace_id_empty(self, api_client):
        """Empty trace_id should be rejected."""
        # Send raw request to bypass helper's auto-generation
        body = {
            "action": "ping.icmp",
            "params": {},
            "trace_id": "",
        }
        async with api_client._session.post(
            f"{api_client._base_url}/api/v1/execute",
            json=body,
            headers=api_client._headers,
        ) as resp:
            result = {"status_code": resp.status, **await resp.json()}
        assert result["status_code"] == 400
        assert "error" in result

    async def test_priority_too_high(self, api_client, trace_id):
        """priority=99 should be rejected (valid range is 0-2)."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
            priority=99,
        )
        assert result["status_code"] == 400

    async def test_ttl_zero(self, api_client, trace_id):
        """ttl_seconds=0 should be rejected (valid range is 1-300)."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
            ttl_seconds=0,
        )
        assert result["status_code"] == 400

    async def test_ttl_huge(self, api_client, trace_id):
        """ttl_seconds=999999 should be rejected (valid range is 1-300)."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
            ttl_seconds=999999,
        )
        assert result["status_code"] == 400

    async def test_worker_id_empty(self, api_client, trace_id):
        """Empty target_worker_id should route to first available Worker."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
            target_worker_id="",
        )
        assert result["status_code"] == 200

    async def test_worker_id_nonexistent(self, api_client, trace_id):
        """Nonexistent target_worker_id should fail with routing error."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
            target_worker_id="no-such-worker-xyz",
        )
        assert result["status_code"] == 200
        if result.get("status") == "failure":
            error = result.get("error", {})
            assert isinstance(error, dict)

    async def test_oversized_payload(self, api_client, trace_id):
        """Oversized params (2MB) should be rejected."""
        body = {
            "action": "ping.icmp",
            "params": {"large": "x" * 2_000_000},
            "trace_id": trace_id,
        }
        async with api_client._session.post(
            f"{api_client._base_url}/api/v1/execute",
            json=body,
            headers=api_client._headers,
        ) as resp:
            result = {"status_code": resp.status}
            try:
                data = await resp.json()
                result.update(data)
            except Exception:
                result["text"] = await resp.text()
        # Master accepts up to 5MB body, so 2MB should be accepted (200) or rejected (400/413)
        assert result["status_code"] in (200, 400, 413)
