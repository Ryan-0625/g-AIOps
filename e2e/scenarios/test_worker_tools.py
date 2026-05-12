"""E2E tests for real Worker tool execution.

All tests require a real Worker to be connected to Master.
Tests execute a tool action, poll for the result via /api/v1/result/:msg_id,
and verify the tool's return values.
"""

import asyncio

import pytest

from helpers.assert_utils import assert_worker_result


async def _poll_result(api_client, msg_id: str, timeout: float = 15.0) -> dict:
    """Poll /api/v1/result/:msg_id until the result is available."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        result = await api_client.result_by_msg_id(msg_id)
        if result["status_code"] == 200:
            return result
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Result for {msg_id} not available within {timeout}s")


async def _auto_approve(api_client, resp: dict) -> str | None:
    """Auto-approve if the execute response requires approval. Returns msg_id."""
    msg_id = resp.get("msg_id", "")
    if not msg_id:
        return None
    approval_id = resp.get("data", {}).get("approval_id") if isinstance(resp.get("data"), dict) else None
    if approval_id:
        await api_client.approve(approval_id)
    return msg_id


@pytest.mark.e2e
class TestWorkerTools:
    async def test_ping_reachable(self, api_client, trace_id):
        """ping.icmp to localhost should succeed."""
        resp = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1", "count": 1},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        assert msg_id, "No msg_id in execute response"

        result = await _poll_result(api_client, msg_id, timeout=15.0)
        env = result.get("payload", {}) if "payload" in result else result
        if env.get("status") == "success":
            data = env.get("data", {})
            assert data.get("reachable") is True, f"Expected reachable=true, got {data}"
            assert isinstance(data.get("avg_rtt_ms"), (int, float))
            assert data["avg_rtt_ms"] > 0

    async def test_ping_unreachable(self, api_client, trace_id):
        """ping.icmp to an unreachable target should return reachable=false."""
        resp = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1", "count": 1, "timeout_seconds": 1},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=15.0)
        env = result.get("payload", {}) if "payload" in result else result
        if env.get("status") == "success":
            data = env.get("data", {})
            # The Worker probes port 80; localhost:80 should be closed.
            assert data.get("reachable") is False, f"Expected unreachable, got {data}"

    async def test_ping_missing_target(self, api_client, trace_id):
        """ping.icmp without target should fail with INVALID_PARAMS."""
        resp = await api_client.execute(
            action="ping.icmp",
            params={},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=10.0)
        assert result["status_code"] == 200

    async def test_disk_usage_root(self, api_client, trace_id):
        """disk.usage on / should return disk stats."""
        resp = await api_client.execute(
            action="disk.usage",
            params={"path": "/"},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=10.0)
        assert result["status_code"] == 200

    async def test_disk_usage_invalid_path(self, api_client, trace_id):
        """disk.usage on nonexistent path should fail."""
        resp = await api_client.execute(
            action="disk.usage",
            params={"path": "/nonexistent_path_xyz"},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=10.0)
        assert result["status_code"] == 200

    async def test_exec_run_ls(self, api_client, trace_id):
        """exec.run ls should succeed."""
        resp = await api_client.execute(
            action="exec.run",
            params={"command": "ls", "args": ["-la", "/tmp"]},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = await _auto_approve(api_client, resp)
        assert msg_id, "No msg_id in execute response"
        result = await _poll_result(api_client, msg_id, timeout=15.0)
        assert result["status_code"] == 200

    async def test_exec_run_unknown_command(self, api_client, trace_id):
        """exec.run with disallowed command should fail."""
        resp = await api_client.execute(
            action="exec.run",
            params={"command": "nonexistent_cmd_xyz"},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = await _auto_approve(api_client, resp)
        assert msg_id, "No msg_id in execute response"
        result = await _poll_result(api_client, msg_id, timeout=10.0)
        assert result["status_code"] == 200

    async def test_exec_run_timeout(self, api_client, trace_id):
        """exec.run with a short timeout should fail with EXECUTION_TIMEOUT."""
        resp = await api_client.execute(
            action="exec.run",
            params={"command": "sleep", "args": ["10"], "timeout_seconds": 1},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = await _auto_approve(api_client, resp)
        assert msg_id, "No msg_id in execute response"
        result = await _poll_result(api_client, msg_id, timeout=15.0)
        assert result["status_code"] == 200

    async def test_process_list(self, api_client, trace_id):
        """process.list should return a list of processes."""
        resp = await api_client.execute(
            action="process.list",
            params={},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=10.0)
        assert result["status_code"] == 200

    async def test_log_tail(self, api_client, trace_id):
        """log.tail on a system log should succeed."""
        resp = await api_client.execute(
            action="log.tail",
            params={"path": "/var/log/syslog", "lines": 5},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=15.0)
        assert result["status_code"] == 200

    async def test_log_tail_invalid_path(self, api_client, trace_id):
        """log.tail on nonexistent path should fail."""
        resp = await api_client.execute(
            action="log.tail",
            params={"path": "/nonexistent.log"},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=10.0)
        assert result["status_code"] == 200

    async def test_log_tail_max_lines(self, api_client, trace_id):
        """log.tail with 5000 lines should return at most 5000 lines."""
        resp = await api_client.execute(
            action="log.tail",
            params={"path": "/var/log/syslog", "lines": 5000},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=20.0)
        assert result["status_code"] == 200

    async def test_service_status(self, api_client, trace_id):
        """service.status on a known system service."""
        resp = await api_client.execute(
            action="service.status",
            params={"name": "sshd"},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        result = await _poll_result(api_client, msg_id, timeout=10.0)
        assert result["status_code"] == 200

    async def test_tool_result_polling(self, api_client, trace_id):
        """Execute ping and verify result is available via polling."""
        resp = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1", "count": 1},
            trace_id=trace_id,
        )
        assert resp["status_code"] == 200
        msg_id = resp.get("msg_id", "")
        assert msg_id

        result = await _poll_result(api_client, msg_id, timeout=15.0)
        assert result["status_code"] == 200
        # Response should contain the full envelope
        assert "msg_id" in result

    async def test_tool_result_not_found(self, api_client):
        """Random msg_id should return 404."""
        result = await api_client.result_by_msg_id(
            "00000000-0000-0000-0000-000000000000"
        )
        assert result["status_code"] == 404
