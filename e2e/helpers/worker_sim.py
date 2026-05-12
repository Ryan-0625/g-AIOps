"""Worker simulator — connects to Master via WebSocket as a fake Worker."""

import asyncio
from uuid import uuid4

from helpers.ws_client import connect_ws, read_envelope, send_envelope


class WorkerSim:
    """Simulates a Worker connecting to Master over WebSocket.

    Usage::

        worker = WorkerSim(ws_url, cluster_token)
        await worker.register()
        # ... test logic ...
        await worker.disconnect()
    """

    def __init__(self, ws_url: str, cluster_token: str, worker_id: str | None = None):
        self._ws_url = ws_url
        self._cluster_token = cluster_token
        self.worker_id = worker_id or f"e2e-worker-{uuid4().hex[:8]}"
        self._ws = None

    async def register(self):
        """Connect to Master, authenticate, and send capability.advertise.

        Matches the envelope format expected by Master's ws-server.ts:
        - msg_type: "request"
        - payload.action: "capability.advertise"
        - payload.params: worker capabilities
        """
        self._ws = await connect_ws(self._ws_url, self._cluster_token)

        # Advertise capabilities in the format Master expects
        await send_envelope(self._ws, {
            "proto_version": "1.0",
            "trace_id": str(uuid4()),
            "msg_id": str(uuid4()),
            "msg_type": "request",
            "timestamp": int(asyncio.get_event_loop().time()),
            "source": "worker",
            "source_id": self.worker_id,
            "target": "master",
            "target_id": "master",
            "correlation_id": "",
            "priority": 0,
            "ttl_seconds": 60,
            "payload": {
                "action": "capability.advertise",
                "params": {
                    "actions": ["sim.echo", "sim.status", "sim.ping",
                                "sim.latency"],
                    "risk_levels": {
                        "sim.echo": "readonly",
                        "sim.status": "readonly",
                        "sim.ping": "readonly",
                        "sim.latency": "readonly",
                    },
                    "worker_version": "0.1.0",
                    "heartbeat_interval": 15,
                    "max_concurrent": 5,
                },
                "status": "pending",
            },
        })

    async def wait_for_request(self, timeout: float = 10.0) -> dict | None:
        """Wait for a request envelope from Master.

        Returns the envelope dict, or None on disconnect.
        Raises TimeoutError if no request arrives within *timeout* seconds.
        """
        return await read_envelope(self._ws, timeout=timeout)

    async def send_response(
        self,
        trace_id: str,
        msg_id: str,
        action: str = "",
        status: str = "success",
        data: dict | None = None,
        error: dict | None = None,
    ):
        """Send a response envelope back to Master."""
        await send_envelope(self._ws, {
            "proto_version": "1.0",
            "trace_id": trace_id,
            "msg_id": msg_id,
            "msg_type": "response",
            "timestamp": int(asyncio.get_event_loop().time()),
            "source": "worker",
            "source_id": self.worker_id,
            "target": "master",
            "target_id": "master",
            "correlation_id": msg_id,
            "priority": 0,
            "ttl_seconds": 30,
            "payload": {
                "action": action,
                "params": {},
                "status": status,
                "data": data or {},
                "error": error,
            },
        })

    async def disconnect(self):
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None

    @property
    def is_connected(self) -> bool:
        """True if the WebSocket is still open."""
        import websockets
        return self._ws is not None and self._ws.state is websockets.protocol.State.OPEN
