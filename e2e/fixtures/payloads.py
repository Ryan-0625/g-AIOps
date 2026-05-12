"""Factory functions for test request bodies and envelopes."""

from uuid import uuid4

# Standard low-risk actions that any Worker should support
LOW_RISK_ACTIONS = ["ping.icmp", "disk.usage"]

# High-risk actions that trigger the approval flow
HIGH_RISK_ACTIONS = ["exec.run", "service.restart", "service.stop"]

# Action that no Worker advertises — used to test routing failures
UNKNOWN_ACTION = "nonexistent.tool"


def make_execute_body(
    action: str = "ping.icmp",
    params: dict | None = None,
    trace_id: str | None = None,
    priority: int = 0,
    ttl_seconds: int = 30,
    target_worker_id: str | None = None,
) -> dict:
    """Create a standard /api/v1/execute request body."""
    body: dict = {
        "action": action,
        "params": params or {},
        "trace_id": trace_id or str(uuid4()),
        "priority": priority,
        "ttl_seconds": ttl_seconds,
    }
    if target_worker_id:
        body["target_worker_id"] = target_worker_id
    return body


def make_envelope(
    msg_type: str = "request",
    trace_id: str | None = None,
    msg_id: str | None = None,
    source: str = "brain",
    source_id: str = "brain",
    target: str = "worker",
    target_id: str = "*",
    action: str = "ping.icmp",
    params: dict | None = None,
    status: str = "pending",
    data: dict | None = None,
    error: dict | None = None,
) -> dict:
    """Create an Envelope Protocol v1 message dict."""
    payload: dict = {"action": action, "params": params or {}, "status": status}
    if data is not None:
        payload["data"] = data
    if error is not None:
        payload["error"] = error

    return {
        "proto_version": "1.0",
        "trace_id": trace_id or str(uuid4()),
        "msg_id": msg_id or str(uuid4()),
        "msg_type": msg_type,
        "timestamp": 0,  # will be set by recipient
        "source": source,
        "source_id": source_id,
        "target": target,
        "target_id": target_id,
        "correlation_id": "",
        "priority": 0,
        "ttl_seconds": 30,
        "payload": payload,
    }
