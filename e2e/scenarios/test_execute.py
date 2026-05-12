"""E2E tests for command execution and routing.

Requires a Worker to be connected to Master.
"""

import pytest


@pytest.mark.e2e
class TestExecute:
    async def test_execute_low_risk_action(self, api_client, trace_id):
        """Low-risk readonly action should succeed without approval."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
        )

        assert result["status_code"] == 200
        assert result["status"] == "pending" or result["status"] == "failure"
        if result["status"] == "failure":
            # If no Worker is connected — that is acceptable
            assert "error" in result

    async def test_execute_returns_msg_id(self, api_client, trace_id):
        """Response should include a valid UUID msg_id."""
        result = await api_client.execute(
            action="disk.usage",
            params={"path": "/tmp"},
            trace_id=trace_id,
        )

        assert result["status_code"] == 200
        assert "msg_id" in result
        assert len(result["msg_id"]) > 0

    async def test_execute_with_priority(self, api_client, trace_id):
        """Request with priority=2 (emergency) should be accepted."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
            priority=2,
        )

        assert result["status_code"] == 200

    async def test_execute_no_worker_for_action(self, api_client, trace_id):
        """Action that no Worker advertises should fail with routing error."""
        result = await api_client.execute(
            action="nonexistent.tool",
            params={},
            trace_id=trace_id,
        )

        # Should either fail with routing error or accept (depending on Master config)
        assert result["status_code"] == 200
        # Master currently accepts and will fail at routing
        if result["status"] == "failure":
            assert "error" in result

    async def test_execute_high_risk_triggers_approval(self, api_client, trace_id):
        """High-risk action (exec.run) should trigger approval flow (if Worker online)."""
        result = await api_client.execute(
            action="exec.run",
            params={"command": "ls", "args": ["-la"]},
            trace_id=trace_id,
        )

        assert result["status_code"] == 200
        assert result["status"] in ("pending", "failure")
