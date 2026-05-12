"""WebSocket client helper — connect to Master and exchange envelopes."""

import asyncio
import json

import websockets


async def connect_ws(ws_url: str, cluster_token: str):
    """Connect to Master WebSocket and return the connection.

    Uses Bearer token via the HTTP Authorization header (WebSocket upgrade),
    matching the Master's ws-server.ts authentication flow.

    The caller MUST close the connection when done::

        ws = await connect_ws(url, token)
        try:
            ...
        finally:
            await ws.close()
    """
    headers = {"Authorization": f"Bearer {cluster_token}"}
    ws = await websockets.connect(ws_url, additional_headers=headers)
    return ws


async def read_envelope(ws, timeout: float = 10.0) -> dict | None:
    """Read a single JSON envelope from the WebSocket.

    Returns None if the connection is closed.
    Raises TimeoutError if no message arrives within *timeout* seconds.
    """
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"No message received within {timeout}s")
    except websockets.ConnectionClosed:
        return None

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


async def send_envelope(ws, envelope: dict):
    """Send a JSON envelope over the WebSocket."""
    await ws.send(json.dumps(envelope))
