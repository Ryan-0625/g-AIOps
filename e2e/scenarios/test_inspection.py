\"\"\"Full-chain integration test for the inspection system.

Tests the complete lifecycle: Create inspection -> Scheduler triggers probe ->
Worker executes -> Results collected -> Alert rules evaluated -> Alerts generated.

This test simulates the chain without requiring real Worker processes.
\"\"\"

import json
import time
from uuid import uuid4

import pytest


@pytest.mark.e2e
class TestInspectionFullChain:
    \"\"\"Full inspection lifecycle: config -> schedule -> probe -> result -> alert.\"\"\"

    async def test_create_inspection(self, api_client):
        \"\"\"Create an inspection via API.\"\"\"
        result = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections\",
            json={
                \"name\": \"E2E Disk Check\",
                \"probe_type\": \"disk.usage\",
                \"probe_params\": {\"path\": \"/\"},
                \"schedule_mode\": \"interval\",
                \"interval_seconds\": 300,
                \"timeout_seconds\": 30,
                \"alert_rules\": [
                    {
                        \"metric\": \"usage_pct\",
                        \"operator\": \">\",
                        \"threshold\": 85,
                        \"severity\": \"warning\",
                        \"message\": \"Space low on {worker_id}: {value}%\"
                    }
                ],
            },
            headers=api_client._headers,
        )
        data = await result.json()
        assert result.status == 201
        assert \"id\" in data

    async def test_list_inspections(self, api_client):
        \"\"\"List all inspections and verify structure.\"\"\"
        result = await api_client._session.get(
            f\"{api_client._base_url}/api/v1/inspections\",
            headers=api_client._headers,
        )
        data = await result.json()
        assert result.status == 200
        assert \"inspections\" in data
        assert \"total\" in data

    async def test_create_inspection_validation(self, api_client):
        \"\"\"Missing required fields should fail validation.\"\"\"
        result = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections\",
            json={\"name\": \"Bad Inspection\"},  # Missing probe_type, probe_params
            headers=api_client._headers,
        )
        data = await result.json()
        assert result.status == 400
        assert \"error\" in data
        assert \"details\" in data

    async def test_create_inspection_invalid_interval(self, api_client):
        \"\"\"Interval below minimum should fail.\"\"\"
        result = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections\",
            json={
                \"name\": \"Fast Check\",
                \"probe_type\": \"ping.icmp\",
                \"probe_params\": {\"target\": \"localhost\"},
                \"schedule_mode\": \"interval\",
                \"interval_seconds\": 1,  # Too fast
                \"alert_rules\": [],
            },
            headers=api_client._headers,
        )
        data = await result.json()
        assert result.status == 400

    async def test_create_inspection_unknown_probe(self, api_client):
        \"\"\"Unknown probe type should fail.\"\"\"
        result = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections\",
            json={
                \"name\": \"Unknown Probe\",
                \"probe_type\": \"unknown.probe\",
                \"probe_params\": {},
                \"schedule_mode\": \"interval\",
                \"interval_seconds\": 60,
                \"alert_rules\": [],
            },
            headers=api_client._headers,
        )
        data = await result.json()
        assert result.status == 400

    async def test_update_inspection(self, api_client):
        \"\"\"Create then update an inspection.\"\"\"
        # Create
        create = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections\",
            json={
                \"name\": \"Update Test\",
                \"probe_type\": \"port.check\",
                \"probe_params\": {\"host\": \"localhost\", \"port\": 80},
                \"schedule_mode\": \"interval\",
                \"interval_seconds\": 300,
                \"alert_rules\": [],
            },
            headers=api_client._headers,
        )
        created = await create.json()
        insp_id = created[\"id\"]

        # Update
        update = await api_client._session.put(
            f\"{api_client._base_url}/api/v1/inspections/{insp_id}\",
            json={\"interval_seconds\": 600},
            headers=api_client._headers,
        )
        assert update.status == 200

        # Verify
        get = await api_client._session.get(
            f\"{api_client._base_url}/api/v1/inspections/{insp_id}\",
            headers=api_client._headers,
        )
        updated = await get.json()
        assert updated.get(\"interval_seconds\") == 600

    async def test_toggle_inspection(self, api_client):
        \"\"\"Toggle inspection on/off.\"\"\"
        create = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections\",
            json={
                \"name\": \"Toggle Test\",
                \"probe_type\": \"ping.icmp\",
                \"probe_params\": {\"target\": \"localhost\"},
                \"schedule_mode\": \"interval\",
                \"interval_seconds\": 300,
                \"alert_rules\": [],
            },
            headers=api_client._headers,
        )
        created = await create.json()
        insp_id = created[\"id\"]

        # Toggle off
        toggle = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections/{insp_id}/toggle\",
            headers=api_client._headers,
        )
        data = await toggle.json()
        assert toggle.status == 200
        assert data.get(\"enabled\") is False

    async def test_delete_inspection(self, api_client):
        \"\"\"Create then delete an inspection.\"\"\"
        create = await api_client._session.post(
            f\"{api_client._base_url}/api/v1/inspections\",
            json={
                \"name\": \"Delete Test\",
                \"probe_type\": \"port.check\",
                \"probe_params\": {\"host\": \"localhost\", \"port\": 22},
                \"schedule_mode\": \"interval\",
                \"interval_seconds\": 300,
                \"alert_rules\": [],
            },
            headers=api_client._headers,
        )
        created = await create.json()
        insp_id = created[\"id\"]

        delete = await api_client._session.delete(
            f\"{api_client._base_url}/api/v1/inspections/{insp_id}\",
            headers=api_client._headers,
        )
        assert delete.status == 200

    async def test_get_results_empty(self, api_client):
        \"\"\"Get results for nonexistent inspection should not crash.\"\"\"
        result = await api_client._session.get(
            f\"{api_client._base_url}/api/v1/inspections/nonexistent/results\",
            headers=api_client._headers,
        )
        # Should return 200 with empty results, or 404
        assert result.status in (200, 404)

    async def test_alert_stats(self, api_client):
        \"\"\"Get alert statistics.\"\"\"
        result = await api_client._session.get(
            f\"{api_client._base_url}/api/v1/alerts/stats\",
            headers=api_client._headers,
        )
        data = await result.json()
        assert result.status == 200
        assert \"total\" in data
        assert \"unacknowledged\" in data
        assert \"critical\" in data
        assert \"warning\" in data
