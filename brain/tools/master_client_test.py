"""Tests for MasterClient — HTTP execution with aiohttp test server."""

import json

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from tools.master_client import MasterClient


class MasterClientTest(AioHTTPTestCase):
    async def get_application(self):
        """Set up a test Master REST server."""

        async def execute_handler(request):
            body = await request.json()
            auth = request.headers.get("Authorization", "")
            if "Bearer test-token" not in auth:
                return web.json_response(
                    {"status": "failure", "error": {"code": "AUTH_FAILED"}},
                    status=401,
                )
            return web.json_response({
                "trace_id": body.get("trace_id", ""),
                "msg_id": "test-msg",
                "status": "pending",
                "action": body.get("action", ""),
            })

        app = web.Application()
        app.router.add_post("/api/v1/execute", execute_handler)
        return app

    @unittest_run_loop
    async def test_execute_sends_correct_request(self):
        client = MasterClient(
            api_url=f"http://localhost:{self.server.port}",
            cluster_token="test-token",
            timeout=10.0,
        )
        result = await client.execute(
            action="ping.icmp",
            params={"target": "10.0.0.1"},
            trace_id="test-trace",
        )
        assert result["status"] == "pending"
        assert result["action"] == "ping.icmp"
        assert result["trace_id"] == "test-trace"

    @unittest_run_loop
    async def test_execute_auth_failure(self):
        client = MasterClient(
            api_url=f"http://localhost:{self.server.port}",
            cluster_token="wrong-token",
            timeout=10.0,
        )
        result = await client.execute(action="ping.icmp", trace_id="auth-test")
        assert result["status"] == "failure"
        assert result.get("error", {}).get("code") == "AUTH_FAILED"

    @unittest_run_loop
    async def test_param_filter_rejects_dangerous_params(self):
        client = MasterClient(
            api_url=f"http://localhost:{self.server.port}",
            cluster_token="test-token",
            timeout=10.0,
        )
        # Shell metacharacters should be rejected by ParamFilter without network call.
        result = await client.execute(
            action="exec.run",
            params={"command": "ls; rm -rf /"},
            trace_id="filter-test",
        )
        assert result["status"] == "failure"
        assert result.get("error", {}).get("code") == "PARAM_SANITIZED"

    @unittest_run_loop
    async def test_execute_connection_refused(self):
        """A request to a closed port should return MASTER_UNREACHABLE."""
        client = MasterClient(
            api_url="http://localhost:1",
            cluster_token="test-token",
            timeout=2.0,
        )
        result = await client.execute(action="ping.icmp", trace_id="conn-test")
        assert result["status"] == "failure"
        assert result.get("error", {}).get("code") in ("MASTER_UNREACHABLE", "MASTER_TIMEOUT")

    @unittest_run_loop
    async def test_execute_without_params(self):
        client = MasterClient(
            api_url=f"http://localhost:{self.server.port}",
            cluster_token="test-token",
            timeout=10.0,
        )
        result = await client.execute(action="disk.usage", trace_id="no-params")
        assert result["status"] == "pending"

    @unittest_run_loop
    async def test_close_releases_session(self):
        client = MasterClient(
            api_url=f"http://localhost:{self.server.port}",
            cluster_token="test-token",
        )
        await client.execute(action="ping.icmp", trace_id="close-test")
        assert client._session is not None
        assert not client._session.closed
        await client.close()
        assert client._session.closed
