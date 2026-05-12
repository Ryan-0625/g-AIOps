"""E2E tests for /health endpoint."""

import pytest


@pytest.mark.e2e
class TestHealth:
    async def test_health_returns_ok(self, api_client):
        """GET /health should return status ok with system info."""
        result = await api_client.health()

        assert result["status_code"] == 200
        assert result["status"] == "ok"
        assert isinstance(result["uptime"], (int, float))
        assert "workers" in result
        assert "online" in result["workers"]
        assert "orchestrator" in result
        assert "pending" in result["orchestrator"]
        assert "security" in result
        assert "pendingApprovals" in result["security"]

    async def test_health_has_expected_structure(self, api_client):
        """Health response should have all expected top-level keys."""
        result = await api_client.health()

        assert set(result.keys()) == {
            "status_code",
            "status",
            "uptime",
            "workers",
            "orchestrator",
            "security",
        }
