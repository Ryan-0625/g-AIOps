"""Multi-Provider LLM Manager — inspired by Nine1Bot's flexible provider system.

Supports:
- Multiple LLM providers (Ollama, OpenAI, Anthropic, Gemini, OpenRouter)
- OpenAI-compatible protocol (any proxy/service that speaks OpenAI API)
- Anthropic-compatible protocol
- Hot-reloadable provider config (no restart needed)
- Automatic fallback (primary → secondary → tertiary)
- Per-provider model lists and capabilities
- Provider health checking

Usage:
    manager = ProviderManager()
    await manager.register_provider("ollama", "ollama", {
        "base_url": "http://localhost:11434",
        "models": [{"id": "qwen2.5:7b"}]
    })
    response = await manager.chat("ollama", "qwen2.5:7b", messages)
"""

import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, AsyncGenerator
from enum import Enum


class ProviderProtocol(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


@dataclass
class ModelInfo:
    id: str
    name: str = ""
    provider: str = ""
    capabilities: list[str] = field(default_factory=lambda: ["chat"])
    max_tokens: int = 8192
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_embeddings: bool = False


@dataclass
class ProviderConfig:
    name: str
    protocol: ProviderProtocol
    base_url: str = ""
    api_key: str = ""
    models: list[ModelInfo] = field(default_factory=list)
    timeout_seconds: float = 60.0
    max_retries: int = 2
    priority: int = 0  # Lower = higher priority
    enabled: bool = True
    health_check_model: str = ""


@dataclass
class ProviderHealth:
    provider: str
    healthy: bool
    latency_ms: float = 0.0
    error: str = ""
    last_check: float = 0.0


# --- Provider Implementations ---


class LLMProvider(ABC):
    """Abstract LLM provider."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        ...

    @abstractmethod
    async def embed(self, model: str, text: str) -> list[float]:
        ...

    @abstractmethod
    async def health(self) -> ProviderHealth:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs (OpenAI, OpenRouter, and any proxy)."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._session: Optional[Any] = None  # aiohttp.ClientSession

    async def _get_session(self):
        if self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        session = await self._get_session()
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        body = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            body["tools"] = tools

        async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"OpenAI API error {resp.status}: {error_text}")
            return await resp.json()

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        session = await self._get_session()
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"

        body = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        async with session.post(url, json=body) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"OpenAI API error {resp.status}: {error_text}")
            async for line in resp.content:
                line = line.decode("utf-8", errors="ignore").strip()
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue

    async def embed(self, model: str, text: str) -> list[float]:
        session = await self._get_session()
        url = f"{self.config.base_url.rstrip('/')}/embeddings"

        body = {
            "model": model,
            "input": text,
        }

        async with session.post(url, json=body) as resp:
            if resp.status != 200:
                raise Exception(f"Embedding API error {resp.status}")
            result = await resp.json()
            return result["data"][0]["embedding"]

    async def health(self) -> ProviderHealth:
        t0 = time.time()
        try:
            session = await self._get_session()
            url = f"{self.config.base_url.rstrip('/')}/models"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                latency = (time.time() - t0) * 1000
                return ProviderHealth(
                    provider=self.config.name,
                    healthy=resp.status == 200,
                    latency_ms=round(latency, 2),
                    last_check=time.time(),
                )
        except Exception as e:
            return ProviderHealth(
                provider=self.config.name,
                healthy=False,
                error=str(e),
                last_check=time.time(),
            )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# --- Manager ---


class ProviderManager:
    """Manages multiple LLM providers with fallback and hot-reload."""

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._configs: dict[str, ProviderConfig] = {}
        self._health_cache: dict[str, ProviderHealth] = {}
        self._lock = asyncio.Lock()
        self._primary_provider: Optional[str] = None
        self._fallback_order: list[str] = []

    async def register_provider(
        self,
        name: str,
        protocol: str,
        config: dict[str, Any],
    ) -> None:
        """Register a new LLM provider. Can be called at runtime (hot-reload)."""
        protocol_enum = ProviderProtocol(protocol.lower())

        models = []
        for m in config.get("models", []):
            models.append(ModelInfo(
                id=m.get("id", ""),
                name=m.get("name", m.get("id", "")),
                provider=name,
                capabilities=m.get("capabilities", ["chat"]),
                max_tokens=m.get("max_tokens", 8192),
                supports_tools=m.get("supports_tools", True),
                supports_embeddings=m.get("supports_embeddings", False),
            ))

        provider_config = ProviderConfig(
            name=name,
            protocol=protocol_enum,
            base_url=config.get("base_url", ""),
            api_key=config.get("api_key", ""),
            models=models,
            timeout_seconds=config.get("timeout_seconds", 60.0),
            max_retries=config.get("max_retries", 2),
            priority=config.get("priority", 0),
            enabled=config.get("enabled", True),
            health_check_model=config.get("health_check_model", ""),
        )

        async with self._lock:
            # Close existing provider if re-registering
            if name in self._providers:
                await self._providers[name].close()

            provider = self._create_provider(provider_config)
            self._providers[name] = provider
            self._configs[name] = provider_config
            self._update_ordering()

    def _create_provider(self, config: ProviderConfig) -> LLMProvider:
        if config.protocol in (ProviderProtocol.OPENAI, ProviderProtocol.OPENROUTER):
            return OpenAICompatibleProvider(config)
        elif config.protocol == ProviderProtocol.OLLAMA:
            # Ollama uses OpenAI-compatible API
            return OpenAICompatibleProvider(config)
        elif config.protocol == ProviderProtocol.ANTHROPIC:
            # Fall back to OpenAI-compatible for now; add Anthropic SDK later
            return OpenAICompatibleProvider(config)
        else:
            return OpenAICompatibleProvider(config)

    def _update_ordering(self) -> None:
        """Sort providers by priority for fallback ordering."""
        enabled = [
            (name, cfg.priority)
            for name, cfg in self._configs.items()
            if cfg.enabled
        ]
        enabled.sort(key=lambda x: x[1])
        self._fallback_order = [name for name, _ in enabled]
        if self._fallback_order:
            self._primary_provider = self._fallback_order[0]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        allow_fallback: bool = True,
    ) -> dict[str, Any]:
        """Chat with automatic fallback across providers."""
        providers_to_try = []
        if provider_name:
            providers_to_try.append(provider_name)
        if allow_fallback:
            providers_to_try.extend(
                p for p in self._fallback_order
                if p != provider_name
            )

        last_error = None
        for prov_name in providers_to_try:
            provider = self._providers.get(prov_name)
            if not provider:
                continue

            # Resolve model
            resolved_model = model or self._get_default_model(prov_name)
            if not resolved_model:
                continue

            try:
                return await provider.chat(
                    resolved_model, messages, tools, timeout
                )
            except Exception as e:
                last_error = e
                continue

        raise Exception(
            f"All providers failed. Last error: {last_error}"
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streaming chat with fallback."""
        providers_to_try = []
        if provider_name:
            providers_to_try.append(provider_name)
        providers_to_try.extend(
            p for p in self._fallback_order
            if p != provider_name
        )

        for prov_name in providers_to_try:
            provider = self._providers.get(prov_name)
            if not provider:
                continue

            resolved_model = model or self._get_default_model(prov_name)
            if not resolved_model:
                continue

            try:
                async for chunk in provider.chat_stream(resolved_model, messages, tools):
                    yield chunk
                return  # Successful stream completed
            except Exception:
                continue

        raise Exception("All providers failed for streaming")

    async def embed(
        self,
        text: str,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[float]:
        """Get embeddings from the best available provider."""
        providers_to_check = []
        if provider_name:
            providers_to_check.append(provider_name)
        providers_to_check.extend(self._fallback_order)

        for prov_name in providers_to_check:
            provider = self._providers.get(prov_name)
            if not provider:
                continue

            resolved_model = model or self._get_embedding_model(prov_name)
            if not resolved_model:
                continue

            try:
                return await provider.embed(resolved_model, text)
            except Exception:
                continue

        raise Exception("No embedding provider available")

    async def health_check_all(self) -> dict[str, ProviderHealth]:
        """Check health of all registered providers."""
        results = {}
        for name, provider in self._providers.items():
            health = await provider.health()
            self._health_cache[name] = health
            results[name] = health
        return results

    def get_provider(self, name: str) -> Optional[LLMProvider]:
        return self._providers.get(name)

    def get_config(self, name: str) -> Optional[ProviderConfig]:
        return self._configs.get(name)

    def list_providers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "protocol": cfg.protocol.value,
                "models": [m.id for m in cfg.models],
                "enabled": cfg.enabled,
                "priority": cfg.priority,
            }
            for name, cfg in self._configs.items()
        ]

    def _get_default_model(self, provider_name: str) -> Optional[str]:
        config = self._configs.get(provider_name)
        if config and config.models:
            return config.models[0].id
        return None

    def _get_embedding_model(self, provider_name: str) -> Optional[str]:
        config = self._configs.get(provider_name)
        if config:
            for model in config.models:
                if model.supports_embeddings:
                    return model.id
        return None

    async def close_all(self) -> None:
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
        self._configs.clear()

    @classmethod
    def from_env(cls) -> "ProviderManager":
        """Auto-configure from environment variables."""
        manager = cls()

        # Ollama
        if os.environ.get("OLLAMA_URL"):
            import asyncio
            asyncio.ensure_future(manager.register_provider(
                "ollama", "ollama", {
                    "base_url": os.environ["OLLAMA_URL"],
                    "models": [{"id": os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")}],
                    "priority": 0,
                }
            ))

        # OpenAI
        if os.environ.get("OPENAI_API_KEY"):
            import asyncio
            asyncio.ensure_future(manager.register_provider(
                "openai", "openai", {
                    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                    "api_key": os.environ["OPENAI_API_KEY"],
                    "models": [{"id": os.environ.get("OPENAI_MODEL", "gpt-4o")}],
                    "priority": 1,
                }
            ))

        return manager
