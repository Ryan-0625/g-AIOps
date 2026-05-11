"""OpenAI adapter using the openai library for async completion."""

import json
from typing import Any, AsyncGenerator

from .adapter import LLMAdapter


class OpenAIAdapter(LLMAdapter):
    """Adapter for OpenAI-compatible APIs (OpenAI, Azure, vLLM, etc.)."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        timeout: float = 60.0,
    ):
        from openai import AsyncOpenAI  # lazy import: only needed for OpenAI adapter

        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key or "sk-placeholder",
            base_url=base_url,
            timeout=timeout,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": True,
            }
            if tools:
                kwargs["tools"] = tools

            stream = await self.client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    part: dict[str, Any] = {}
                    if delta.content:
                        part["content"] = delta.content
                    if delta.tool_calls:
                        part["tool_calls"] = [
                            {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in delta.tool_calls
                        ]
                    if part:
                        yield part
        except Exception as e:
            yield {"error": f"OPENAI_ERROR: {e}"}

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "timeout": timeout,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            completion = await self.client.chat.completions.create(**kwargs)
            choice = completion.choices[0] if completion.choices else None
            if not choice:
                return {"message": {"content": ""}}

            msg = choice.message
            result: dict[str, Any] = {"message": {"role": "assistant"}}
            if msg.content:
                result["message"]["content"] = msg.content
            if msg.tool_calls:
                result["message"]["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]
            return result
        except Exception as e:
            return {"error": f"OPENAI_ERROR: {e}", "message": {"content": ""}}

    async def close(self) -> None:
        await self.client.close()
