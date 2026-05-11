"""Ollama adapter using aiohttp for async HTTP streaming."""

import asyncio
import json
from typing import Any, AsyncGenerator

import aiohttp

from .adapter import LLMAdapter


class OllamaAdapter(LLMAdapter):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        session = await self._ensure_session()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        try:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.content:
                    if line.strip():
                        try:
                            yield json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            yield {"error": f"INVALID_JSON: {line.decode('utf-8')[:200]}"}
        except asyncio.TimeoutError:
            yield {"error": "STREAM_TIMEOUT"}
        except aiohttp.ClientError as e:
            yield {"error": f"CONNECTION_ERROR: {e}"}
        except Exception as e:
            yield {"error": f"UNEXPECTED_ERROR: {e}"}

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        session = await self._ensure_session()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        async with session.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
