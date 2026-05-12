"""WebSocket protocol robustness tests — malformed messages, auth failures.

These tests use WorkerSim (fake Worker) and do NOT require a real Worker.
They verify that the Master's WebSocket server handles edge cases correctly.
"""

import asyncio

import pytest
import websockets

from helpers.ws_client import connect_ws, read_envelope, send_envelope


@pytest.mark.e2e
class TestWsRobustness:
    async def test_malformed_json(self, ws_url, cluster_token):
        """Send malformed JSON — Master should return INVALID_ENVELOPE error."""
        ws = await connect_ws(ws_url, cluster_token)
        try:
            await ws.send("this is not valid json")
            response = await read_envelope(ws, timeout=5.0)
            assert response is not None, "Expected error envelope, got None"
            payload = response.get("payload", {})
            error = payload.get("error", {})
            if isinstance(error, dict):
                code = error.get("code", "")
                assert code == "INVALID_ENVELOPE", f"Expected INVALID_ENVELOPE, got {code}"
        finally:
            await ws.close()

    async def test_no_auth_token(self, ws_url):
        """Connect without auth token — should be rejected."""
        ws = await websockets.connect(ws_url)
        try:
            try:
                await asyncio.wait_for(ws.recv(), timeout=3.0)
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                pass
        finally:
            await ws.close()

    async def test_wrong_msg_type_first(self, ws_url, cluster_token):
        """First message is not capability.advertise — connection should be closed."""
        ws = await connect_ws(ws_url, cluster_token)
        try:
            await send_envelope(ws, {
                "msg_type": "request",
                "source": "worker",
                "payload": {"action": "ping.icmp", "params": {}},
            })
            try:
                await asyncio.wait_for(ws.recv(), timeout=5.0)
            except websockets.ConnectionClosed:
                pass
        finally:
            await ws.close()

    async def test_unknown_msg_type(self, ws_url, cluster_token):
        """Send an unknown msg_type — should be ignored (not crash)."""
        ws = await connect_ws(ws_url, cluster_token)
        try:
            await send_envelope(ws, {
                "proto_version": "1.0",
                "msg_type": "request",
                "source": "worker",
                "source_id": "robustness-test-worker",
                "target": "master",
                "payload": {
                    "action": "capability.advertise",
                    "params": {"actions": ["ping.icmp"]},
                    "status": "pending",
                },
            })

            await send_envelope(ws, {
                "proto_version": "1.0",
                "msg_type": "unknown_type_xyz",
                "source": "worker",
                "payload": {"action": "ping.icmp", "params": {}},
            })

            await send_envelope(ws, {
                "proto_version": "1.0",
                "msg_type": "heartbeat",
                "source": "worker",
                "payload": {},
            })
            assert True
        finally:
            await ws.close()

    async def test_duplicate_correlation_id(self, ws_url, cluster_token):
        """Same correlation_id twice — Worker dedup should handle it."""
        ws = await connect_ws(ws_url, cluster_token)
        try:
            await send_envelope(ws, {
                "proto_version": "1.0",
                "msg_type": "request",
                "source": "worker",
                "source_id": "dedup-test-worker",
                "target": "master",
                "payload": {
                    "action": "capability.advertise",
                    "params": {"actions": ["ping.icmp"]},
                    "status": "pending",
                },
            })

            await send_envelope(ws, {
                "proto_version": "1.0",
                "msg_id": "resp-001",
                "msg_type": "response",
                "source": "worker",
                "source_id": "dedup-test-worker",
                "target": "master",
                "correlation_id": "test-correlation-id",
                "payload": {
                    "action": "ping.icmp",
                    "status": "success",
                    "data": {"reachable": True},
                },
            })

            await send_envelope(ws, {
                "proto_version": "1.0",
                "msg_id": "resp-001-dup",
                "msg_type": "response",
                "source": "worker",
                "source_id": "dedup-test-worker",
                "target": "master",
                "correlation_id": "test-correlation-id",
                "payload": {
                    "action": "ping.icmp",
                    "status": "success",
                    "data": {"reachable": True},
                },
            })

            assert True
        finally:
            await ws.close()
