"""Shared assertion helpers for E2E tests."""

import asyncio


def assert_envelope_structure(env: dict):
    """Verify that a response envelope has the expected top-level fields."""
    assert "msg_id" in env, "Missing msg_id in envelope"
    assert "msg_type" in env, "Missing msg_type in envelope"
    assert "payload" in env, "Missing payload in envelope"
    assert "source" in env, "Missing source in envelope"
    assert "target" in env, "Missing target in envelope"
    assert "timestamp" in env, "Missing timestamp in envelope"


def assert_worker_result(env: dict, action: str, expected_keys: list[str]):
    """Verify a Worker execution result envelope.

    Checks that the envelope contains a successful response with the expected
    data keys in the payload.
    """
    assert_envelope_structure(env)
    assert env["msg_type"] == "response", f"Expected response, got {env['msg_type']}"
    assert env["payload"]["status"] == "success", (
        f"Expected success, got {env['payload'].get('status')}"
    )
    assert env["payload"]["action"] == action, (
        f"Expected action {action}, got {env['payload'].get('action')}"
    )
    data = env["payload"].get("data", {})
    for key in expected_keys:
        assert key in data, f"Missing expected key '{key}' in payload.data"


async def within_timeout(coro, timeout: float = 10.0):
    """Run a coroutine with a timeout. Raises TimeoutError on expiry."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Operation timed out after {timeout}s")
