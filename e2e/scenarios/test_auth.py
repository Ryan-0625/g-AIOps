"""E2E tests for authentication and request validation."""

import pytest


@pytest.mark.e2e
class TestAuth:
    async def test_execute_no_token(self, api_client):
        """Request without token should return 401."""
        result = await api_client.execute(
            action="ping.icmp",
            token_override="",  # empty token
        )
        assert result["status_code"] == 401

    async def test_execute_invalid_token(self, api_client):
        """Request with wrong token should return 401."""
        result = await api_client.execute(
            action="ping.icmp",
            token_override="this-is-wrong",
        )
        assert result["status_code"] == 401

    async def test_execute_missing_trace_id(self, api_client):
        """Request without trace_id should return 400."""
        # Send raw request to bypass helper's automatic trace_id generation
        headers = {
            "Authorization": f"Bearer {api_client._headers['Authorization'].split()[1]}",
            "Content-Type": "application/json",
        }
        body = {"action": "ping.icmp", "params": {}}
        async with api_client._session.post(
            f"{api_client._base_url}/api/v1/execute",
            json=body,
            headers=headers,
        ) as resp:
            assert resp.status == 400

    async def test_execute_missing_action(self, api_client, trace_id):
        """Request without action should return 400."""
        result = await api_client.execute(
            action="",
            trace_id=trace_id,
        )
        assert result["status_code"] == 400

    async def test_execute_valid_request(self, api_client, trace_id):
        """Fully valid request should return 200 (pending if Worker online, failure if none)."""
        result = await api_client.execute(
            action="ping.icmp",
            params={"target": "127.0.0.1"},
            trace_id=trace_id,
        )

        assert result["status_code"] == 200
        assert result["status"] in ("pending", "failure")
        assert "trace_id" in result
        assert "msg_id" in result

    async def test_execute_invalid_body_not_json(self, api_client):
        """Non-JSON body should return 400."""
        import aiohttp

        headers = {
            "Authorization": f"Bearer {api_client._headers['Authorization'].split()[1]}",
            "Content-Type": "application/json",
        }
        async with api_client._session.post(
            f"{api_client._base_url}/api/v1/execute",
            data=b"not json",
            headers=headers,
        ) as resp:
            assert resp.status == 400
