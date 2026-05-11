"""Master API client — sends Brain requests to Master via REST."""

import asyncio
import json
from typing import Any

import aiohttp

from logger.structured_logger import get_logger
from logger.trace_context import generate_trace_id, generate_msg_id
from safety.param_filter import ParamFilter

logger = get_logger()
param_filter = ParamFilter()


class MasterClient:
    def __init__(self, api_url: str, cluster_token: str, timeout: float = 30.0):
        self.api_url = api_url.rstrip("/")
        self.cluster_token = cluster_token
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
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
