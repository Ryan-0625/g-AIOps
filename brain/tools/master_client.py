"""Master API client — sends Brain requests to Master via REST."""

import asyncio
import json
import time
from typing import Any

import aiohttp

from logger.structured_logger import get_logger
from logger.trace_context import generate_trace_id, generate_msg_id
from safety.param_filter import ParamFilter

logger = get_logger()
param_filter = ParamFilter()


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter (参照 master/src/server/flow-control.ts).

    Tracks request timestamps per key in a deque and rejects once the
    window is full. Thread-safe for asyncio usage.
    """

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []

    def allow(self) -> bool:
        """Check and record a request. Returns True if under the limit."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        # Prune expired timestamps.
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        if len(self._timestamps) >= self.max_requests:
            return False
        self._timestamps.append(now)
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.max_requests - len(self._timestamps))


class MasterClient:
    def __init__(
        self,
        api_url: str,
        cluster_token: str,
        timeout: float = 30.0,
        max_requests_per_minute: int = 60,
        tls_verify: bool = True,
    ):
        self.api_url = api_url.rstrip("/")
        self.cluster_token = cluster_token
        self.timeout = timeout
        self.tls_verify = tls_verify
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = SlidingWindowRateLimiter(
            max_requests=max_requests_per_minute,
            window_seconds=60,
        )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = None
            if not self.tls_verify and self.api_url.startswith("https"):
                import ssl
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def execute(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        trace_id: str | None = None,
        priority: int = 0,
        ttl_seconds: int = 30,
    ) -> dict[str, Any]:
        """Send an instruction to Master.

        The instruction passes through ParamFilter before being sent.
        If rejected, returns an error response without consuming network.
        """
        trace_id = trace_id or generate_trace_id()

        # ParamFilter — reject dangerous params before they reach the network.
        filter_result = param_filter.filter(action, params or {})
        if filter_result.rejected:
            logger.warning(
                "instruction rejected by ParamFilter",
                extra={
                    "action": action,
                    "error_code": "PARAM_SANITIZED",
                    "data": {"reason": filter_result.reason, "trace_id": trace_id},
                },
            )
            return {
                "trace_id": trace_id,
                "status": "failure",
                "action": action,
                "error": {
                    "code": "PARAM_SANITIZED",
                    "message": filter_result.reason,
                },
            }

        # Rate limiter — avoid overwhelming Master.
        if not self._rate_limiter.allow():
            logger.warning(
                "Master rate limit reached, throttling request",
                extra={
                    "action": action,
                    "error_code": "MASTER_CLIENT_RATE_LIMITED",
                    "data": {"trace_id": trace_id},
                },
            )
            return {
                "trace_id": trace_id,
                "status": "failure",
                "action": action,
                "error": {
                    "code": "MASTER_CLIENT_RATE_LIMITED",
                    "message": "Request throttled: Master rate limit reached",
                },
            }

        # Build request.
        body = {
            "action": action,
            "params": filter_result.sanitized_params,
            "trace_id": trace_id,
            "priority": priority,
            "ttl_seconds": ttl_seconds,
        }

        session = await self._ensure_session()
        headers = {
            "Authorization": f"Bearer {self.cluster_token}",
            "Content-Type": "application/json",
        }

        try:
            async with session.post(
                f"{self.api_url}/api/v1/execute",
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                result = await resp.json()
                return result
        except asyncio.TimeoutError:
            return {
                "trace_id": trace_id,
                "status": "failure",
                "action": action,
                "error": {"code": "MASTER_TIMEOUT", "message": "Master did not respond in time"},
            }
        except aiohttp.ClientError as e:
            return {
                "trace_id": trace_id,
                "status": "failure",
                "action": action,
                "error": {"code": "MASTER_UNREACHABLE", "message": str(e)},
            }

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
