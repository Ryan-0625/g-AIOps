"""E2E tests for WebSocket protocol.

Connects a simulated Worker to Master via WebSocket and tests
the full message exchange cycle.
"""

import asyncio
from uuid import uuid4

import pytest

from helpers.worker_sim import WorkerSim
from helpers.ws_client import read_envelope


WS_TIMEOUT = 15.0


@pytest.mark.e2e
class TestWebSocket:
    async def test_ws_handshake(self, ws_url, cluster_token):
        """Worker can connect and register via capability.advertise."""
        worker = WorkerSim(ws_url, cluster_token)
        try:
            await worker.register()
            assert worker.is_connected
        finally:
            await worker.disconnect()

    async def test_ws_receive_request(self, ws_url, cluster_token, api_client):
        """Worker receives a request envelope after REST API execute call."""
        worker = WorkerSim(ws_url, cluster_token)
        try:
            await worker.register()

            # Send execute request via REST API
            trace_id = str(uuid4())
            await api_client.execute(
                action="sim.echo",
                params={"message": "hello"},
                trace_id=trace_id,
            )

            # Worker should receive a request envelope
            envelope = await worker.wait_for_request(timeout=WS_TIMEOUT)
            assert envelope is not None
            assert envelope["msg_type"] == "request"
            assert envelope["trace_id"] == trace_id
            assert envelope["payload"]["action"] == "sim.echo"
        finally:
            await worker.disconnect()

    async def test_ws_send_response(self, ws_url, cluster_token, api_client):
        """Worker can send a response back to Master."""
        worker = WorkerSim(ws_url, cluster_token)
        try:
            await worker.register()

            # Send execute request
            trace_id = str(uuid4())
            await api_client.execute(
                action="sim.status",
                params={"check": "ready"},
                trace_id=trace_id,
            )

            # Receive the request envelope
            envelope = await worker.wait_for_request(timeout=WS_TIMEOUT)
            assert envelope is not None

            # Send a response
            await worker.send_response(
                trace_id=envelope["trace_id"],
                msg_id=envelope["msg_id"],
                status="success",
                data={"used": 42, "available": 958},
            )

            # No error means the response was accepted
        finally:
            await worker.disconnect()

    async def test_ws_multiple_requests(self, ws_url, cluster_token, api_client):
        """Worker can handle multiple sequential requests."""
        worker = WorkerSim(ws_url, cluster_token)
        try:
            await worker.register()

            for i in range(3):
                trace_id = str(uuid4())
                await api_client.execute(
                    action="sim.echo",
                    params={"message": f"hello-{i}"},
                    trace_id=trace_id,
                )

                envelope = await worker.wait_for_request(timeout=WS_TIMEOUT)
                assert envelope is not None
                assert envelope["msg_type"] == "request"
                assert envelope["trace_id"] == trace_id

                await worker.send_response(
                    trace_id=envelope["trace_id"],
                    msg_id=envelope["msg_id"],
                    status="success",
                )
        finally:
            await worker.disconnect()

    async def test_ws_worker_connect_increases_count(
        self, ws_url, cluster_token, api_client
    ):
        """Worker connection should increase workers.online in /health."""
        # Check baseline
        before = await api_client.health()
        baseline = before["workers"]["online"]

        # Connect a worker
        worker = WorkerSim(ws_url, cluster_token)
        await worker.register()

        try:
            after = await api_client.health()
            assert after["workers"]["online"] == baseline + 1
        finally:
            await worker.disconnect()
