"""E2E tests for high-risk action approval flow."""

import re

import pytest


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@pytest.mark.e2e
class TestApproval:
    async def test_high_risk_returns_approval_id(self, api_client, trace_id):
        """High-risk action response should include approval_id when Worker online."""
        result = await api_client.execute(
            action="exec.run",
            params={"command": "ls"},
            trace_id=trace_id,
        )

        assert result["status_code"] == 200
        if result.get("status") == "pending":
            # Worker is online — approval flow was triggered
            assert "data" in result
            assert "approval_id" in result["data"]
            assert UUID_PATTERN.match(result["data"]["approval_id"])
        else:
            # No Worker connected — high-risk action fails at routing
            assert result["status"] == "failure"

    async def test_approve_nonexistent(self, api_client):
        """Approving a non-existent ID should return 404."""
        result = await api_client.approve("00000000-0000-0000-0000-000000000000")
        assert result["status_code"] == 404

    async def test_reject_nonexistent(self, api_client):
        """Rejecting a non-existent ID should return 404."""
        result = await api_client.reject("00000000-0000-0000-0000-000000000000")
        assert result["status_code"] == 404

    async def test_approve_reject_flow(self, api_client, trace_id):
        """Full flow: request high-risk → approve → verify (requires Worker)."""
        exec_result = await api_client.execute(
            action="exec.run",
            params={"command": "ls"},
            trace_id=trace_id,
        )
        assert exec_result["status_code"] == 200

        if exec_result.get("status") != "pending":
            pytest.skip("No Worker connected — approval flow not triggered")

        approval_id = exec_result["data"]["approval_id"]

        # Approve it
        approve_result = await api_client.approve(approval_id)
        assert approve_result["status_code"] == 200
