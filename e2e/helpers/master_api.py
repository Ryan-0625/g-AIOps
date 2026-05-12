"""Master REST API client — async wrapper for all Master endpoints."""

import json
from uuid import uuid4

import aiohttp


class MasterAPI:
    """Async REST client for the Master API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        cluster_token: str,
    ):
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {cluster_token}",
            "Content-Type": "application/json",
        }

    # ── Health ────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """GET /health"""
        async with self._session.get(
            f"{self._base_url}/health"
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}

    # ── Execute ───────────────────────────────────────────────────────────

    async def execute(
        self,
        action: str,
        params: dict | None = None,
        trace_id: str | None = None,
        priority: int = 0,
        ttl_seconds: int = 30,
        target_worker_id: str | None = None,
        token_override: str | None = None,
    ) -> dict:
        """POST /api/v1/execute"""
        body = {
            "action": action,
            "params": params or {},
            "trace_id": trace_id or str(uuid4()),
            "priority": priority,
            "ttl_seconds": ttl_seconds,
        }
        if target_worker_id:
            body["target_worker_id"] = target_worker_id

        headers = self._headers
        if token_override is not None:
            headers = {**headers, "Authorization": f"Bearer {token_override}"}

        async with self._session.post(
            f"{self._base_url}/api/v1/execute",
            json=body,
            headers=headers,
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}

    # ── Approval ──────────────────────────────────────────────────────────

    async def approve(self, approval_id: str) -> dict:
        """POST /api/v1/approve/:id"""
        async with self._session.post(
            f"{self._base_url}/api/v1/approve/{approval_id}",
            headers=self._headers,
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}

    async def reject(self, approval_id: str) -> dict:
        """POST /api/v1/reject/:id"""
        async with self._session.post(
            f"{self._base_url}/api/v1/reject/{approval_id}",
            headers=self._headers,
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}

    # ── Traces ────────────────────────────────────────────────────────────

    async def traces(self) -> dict:
        """GET /api/v1/traces"""
        async with self._session.get(
            f"{self._base_url}/api/v1/traces",
            headers=self._headers,
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}

    async def trace_by_id(self, trace_id: str) -> dict:
        """GET /api/v1/trace/:trace_id"""
        async with self._session.get(
            f"{self._base_url}/api/v1/trace/{trace_id}",
            headers=self._headers,
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}

    # ── Result Polling ──────────────────────────────────────────────────────

    async def result_by_msg_id(self, msg_id: str) -> dict:
        """GET /api/v1/result/:msg_id — poll for Worker execution result."""
        async with self._session.get(
            f"{self._base_url}/api/v1/result/{msg_id}",
            headers=self._headers,
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}

    # ── Metrics ───────────────────────────────────────────────────────────

    async def metrics(self) -> dict:
        """GET /metrics"""
        async with self._session.get(
            f"{self._base_url}/metrics"
        ) as resp:
            text = await resp.text()
            return {"status_code": resp.status, "text": text}

    # ── Worker Health (Docker mode only) ───────────────────────────────────

    async def worker_health(self, worker_base_url: str = "http://worker:9090") -> dict:
        """GET /health on the Worker's HTTP health endpoint."""
        async with self._session.get(
            f"{worker_base_url}/health"
        ) as resp:
            return {"status_code": resp.status, **await resp.json()}
