"""Tests for BrainConfig — environment variable loading and defaults."""

from config import BrainConfig


class TestBrainConfig:
    def test_defaults(self):
        cfg = BrainConfig()
        assert cfg.llm_provider == "ollama"
        assert cfg.llm_model == "qwen2.5:7b"
        assert cfg.llm_base_url == "http://localhost:11434"
        assert cfg.llm_timeout == 30.0
        assert cfg.llm_max_retries == 2
        assert cfg.master_api_url == "http://localhost:32080"
        assert cfg.cluster_token == "dev-token"
        assert cfg.master_request_timeout == 30.0
        assert cfg.max_retry_same == 3
        assert cfg.max_total_retries == 5
        assert cfg.log_level == "info"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OLLAMA_MODEL", "gpt-4")
        monkeypatch.setenv("OLLAMA_URL", "http://10.0.0.1:11434")
        monkeypatch.setenv("LLM_TIMEOUT", "60")
        monkeypatch.setenv("LLM_MAX_RETRIES", "5")
        monkeypatch.setenv("MASTER_API_URL", "http://master:32080")
        monkeypatch.setenv("CLUSTER_TOKEN", "prod-token")
        monkeypatch.setenv("MASTER_REQUEST_TIMEOUT", "15")
        monkeypatch.setenv("MAX_RETRY_SAME", "5")
        monkeypatch.setenv("MAX_TOTAL_RETRIES", "10")
        monkeypatch.setenv("LOG_LEVEL", "debug")

        cfg = BrainConfig.from_env()
        assert cfg.llm_provider == "openai"
        assert cfg.llm_model == "gpt-4"
        assert cfg.llm_base_url == "http://10.0.0.1:11434"
        assert cfg.llm_timeout == 60.0
        assert cfg.llm_max_retries == 5
        assert cfg.master_api_url == "http://master:32080"
        assert cfg.cluster_token == "prod-token"
        assert cfg.master_request_timeout == 15.0
        assert cfg.max_retry_same == 5
        assert cfg.max_total_retries == 10
        assert cfg.log_level == "debug"

    def test_from_env_partial_override(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        cfg = BrainConfig.from_env()
        assert cfg.llm_provider == "openai"
        # Unset vars fall back to defaults.
        assert cfg.llm_model == "qwen2.5:7b"
        assert cfg.master_api_url == "http://localhost:32080"

    def test_timeout_zero(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT", "0")
        cfg = BrainConfig.from_env()
        assert cfg.llm_timeout == 0.0
