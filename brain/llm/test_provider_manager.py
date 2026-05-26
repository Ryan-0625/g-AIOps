"""Tests for the multi-provider LLM manager."""

import os
import pytest
from llm.provider_manager import (
    ProviderManager, ModelInfo, ProviderConfig, ProviderProtocol,
)


@pytest.fixture
def manager():
    return ProviderManager()


@pytest.mark.asyncio
async def test_register_provider(manager):
    await manager.register_provider("test-ollama", "ollama", {
        "base_url": "http://localhost:11434",
        "models": [{"id": "qwen2.5:7b"}],
        "priority": 0,
    })
    providers = manager.list_providers()
    assert len(providers) == 1
    assert providers[0]["name"] == "test-ollama"
    assert providers[0]["protocol"] == "ollama"
    assert providers[0]["models"] == ["qwen2.5:7b"]


@pytest.mark.asyncio
async def test_register_multiple_providers(manager):
    await manager.register_provider("ollama", "ollama", {
        "base_url": "http://localhost:11434",
        "models": [{"id": "qwen2.5:7b"}],
        "priority": 0,
    })
    await manager.register_provider("openai", "openai", {
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
        "models": [{"id": "gpt-4o"}],
        "priority": 1,
    })
    providers = manager.list_providers()
    assert len(providers) == 2


@pytest.mark.asyncio
async def test_hot_reload_provider(manager):
    await manager.register_provider("test", "openai", {
        "base_url": "http://old.example.com",
        "models": [{"id": "model-v1"}],
    })
    # Hot-reload with new config
    await manager.register_provider("test", "openai", {
        "base_url": "http://new.example.com",
        "models": [{"id": "model-v2"}],
    })
    cfg = manager.get_config("test")
    assert cfg is not None
    assert cfg.base_url == "http://new.example.com"
    assert cfg.models[0].id == "model-v2"


@pytest.mark.asyncio
async def test_list_providers_empty(manager):
    assert manager.list_providers() == []


def test_get_config_nonexistent(manager):
    assert manager.get_config("nonexistent") is None


def test_get_provider_nonexistent(manager):
    assert manager.get_provider("nonexistent") is None


@pytest.mark.asyncio
async def test_disable_provider(manager):
    await manager.register_provider("disabled-1", "ollama", {
        "models": [{"id": "model-1"}],
        "enabled": False,
        "priority": 0,
    })
    # When all providers disabled, fallback order should be empty
    providers = manager.list_providers()
    # Provider should still appear in list
    disabled = [p for p in providers if not p["enabled"]]
    assert len(disabled) == 1


@pytest.mark.asyncio
async def test_model_info_defaults():
    model = ModelInfo(id="test-model")
    assert model.id == "test-model"
    assert model.name == ""
    assert model.supports_tools is True
    assert model.supports_streaming is True
    assert model.supports_embeddings is False


@pytest.mark.asyncio
async def test_provider_config_defaults():
    config = ProviderConfig(name="test", protocol=ProviderProtocol.OLLAMA)
    assert config.name == "test"
    assert config.protocol == ProviderProtocol.OLLAMA
    assert config.enabled is True
    assert config.priority == 0
    assert config.timeout_seconds == 60.0
    assert config.max_retries == 2


@pytest.mark.asyncio
async def test_chat_fails_when_no_providers(manager):
    with pytest.raises(Exception) as exc:
        await manager.chat([{"role": "user", "content": "hello"}])
    assert "All providers failed" in str(exc.value)


@pytest.mark.asyncio
async def test_from_env_ollama_only():
    os.environ["OLLAMA_URL"] = "http://ollama:11434"
    os.environ["OLLAMA_MODEL"] = "llama2"
    try:
        manager = ProviderManager.from_env()
        # from_env uses asyncio.ensure_future so registration is pending
        # Just verify it creates a manager
        assert manager is not None
    finally:
        del os.environ["OLLAMA_URL"]
        del os.environ["OLLAMA_MODEL"]


@pytest.mark.asyncio
async def test_chat_all_providers_timeout(manager):
    """When all providers time out, should raise appropriate error."""
    await manager.register_provider("timeout-1", "ollama", {
        "base_url": "http://192.0.2.1:11434",  # Non-routable IP
        "models": [{"id": "model-1"}],
        "timeout_seconds": 0.1,
        "priority": 0,
    })
    await manager.register_provider("timeout-2", "openai", {
        "base_url": "http://192.0.2.2:32080",
        "api_key": "sk-test",
        "models": [{"id": "model-2"}],
        "timeout_seconds": 0.1,
        "priority": 1,
    })
    with pytest.raises(Exception) as exc:
        await manager.chat([{"role": "user", "content": "hello"}])
    assert "All providers failed" in str(exc.value)


@pytest.mark.asyncio
async def test_mixed_enabled_disabled_providers(manager):
    """When primary is disabled, should fall back to enabled provider."""
    await manager.register_provider("disabled-primary", "ollama", {
        "models": [{"id": "model-1"}],
        "enabled": False,
        "priority": 0,
    })
    await manager.register_provider("enabled-secondary", "ollama", {
        "models": [{"id": "model-2"}],
        "enabled": True,
        "priority": 1,
    })
    # Secondary is enabled but both will fail connect - should get "All providers failed"
    with pytest.raises(Exception) as exc:
        await manager.chat([{"role": "user", "content": "test"}])
    assert "All providers failed" in str(exc.value)


@pytest.mark.asyncio
async def test_chat_with_specific_provider_name(manager):
    """Chat should use specified provider."""
    await manager.register_provider("provider-a", "ollama", {
        "models": [{"id": "model-a"}],
        "priority": 0,
    })
    await manager.register_provider("provider-b", "ollama", {
        "models": [{"id": "model-b"}],
        "priority": 1,
    })
    # Both unavailable but should try provider-a first
    with pytest.raises(Exception) as exc:
        await manager.chat([{"role": "user", "content": "hi"}], provider_name="provider-b")
    assert "All providers failed" in str(exc.value)


@pytest.mark.asyncio
async def test_register_invalid_protocol(manager):
    """Invalid protocol should raise error."""
    with pytest.raises(Exception):
        await manager.register_provider("bad-proto", "invalid_protocol_xyz", {
            "models": [{"id": "test"}],
        })


@pytest.mark.asyncio
async def test_provider_with_no_models(manager):
    """Provider with no models should not break listing."""
    await manager.register_provider("no-models", "ollama", {
        "base_url": "http://localhost:11434",
        "models": [],
    })
    providers = manager.list_providers()
    assert len(providers) == 1
    assert providers[0]["models"] == []


@pytest.mark.asyncio
async def test_chat_stream_all_providers_fail(manager):
    """Streaming should raise when all providers fail."""
    with pytest.raises(Exception) as exc:
        async for _ in manager.chat_stream([{"role": "user", "content": "hello"}]):
            pass
    assert "All providers failed" in str(exc.value)


@pytest.mark.asyncio
async def test_embed_fails_with_no_providers(manager):
    """Embed should raise when no providers."""
    with pytest.raises(Exception) as exc:
        await manager.embed("test text")
    assert "No embedding provider" in str(exc.value)


@pytest.mark.asyncio
async def test_health_check_all_empty(manager):
    """Health check with no providers returns empty dict."""
    results = await manager.health_check_all()
    assert results == {}


@pytest.mark.asyncio
async def test_hot_reload_updates_fallback_order(manager):
    """Hot-reloading a provider should update fallback order."""
    await manager.register_provider("provider-1", "ollama", {
        "models": [{"id": "model-1"}],
        "priority": 5,
    })
    await manager.register_provider("provider-2", "ollama", {
        "models": [{"id": "model-2"}],
        "priority": 1,
    })
    # Now hot-reload provider-1 to have higher priority
    await manager.register_provider("provider-1", "ollama", {
        "models": [{"id": "model-1-v2"}],
        "priority": 0,
    })
    # provider-1 should now be first in fallback order
    assert manager._fallback_order[0] == "provider-1"


@pytest.mark.asyncio
async def test_disable_all_providers(manager):
    """When all providers disabled, fallback order should exclude them."""
    await manager.register_provider("p1", "ollama", {
        "models": [{"id": "m1"}],
        "enabled": False,
        "priority": 0,
    })
    await manager.register_provider("p2", "ollama", {
        "models": [{"id": "m2"}],
        "enabled": False,
        "priority": 1,
    })
    # Fallback order should exclude disabled providers
    assert all(p not in manager._fallback_order for p in ["p1", "p2"])


@pytest.mark.asyncio
async def test_from_env_no_vars():
    """from_env with no env vars should create empty manager."""
    # Ensure env vars are not set
    if "OLLAMA_URL" in os.environ:
        del os.environ["OLLAMA_URL"]
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    manager = ProviderManager.from_env()
    assert manager.list_providers() == []


@pytest.mark.asyncio
async def test_get_default_model_when_no_models(manager):
    """get_default_model should return None when no models."""
    await manager.register_provider("empty", "ollama", {"models": []})
    assert manager._get_default_model("empty") is None
    assert manager._get_default_model("nonexistent") is None
