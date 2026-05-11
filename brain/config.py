"""Brain configuration — loaded from environment variables with defaults."""

import os
from dataclasses import dataclass


@dataclass
class BrainConfig:
    # LLM
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_base_url: str = "http://localhost:11434"
    llm_timeout: float = 30.0
    llm_max_retries: int = 2

    # Master API
    master_api_url: str = "http://localhost:8080"
    cluster_token: str = "dev-token"
    master_request_timeout: float = 30.0
    tls_verify: bool = True

    # Engine
    max_retry_same: int = 3
    max_total_retries: int = 5

    # Degradation / Read-Only
    read_only: bool = False

    # Logging
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "BrainConfig":
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
            llm_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            llm_base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            llm_timeout=float(os.getenv("LLM_TIMEOUT", "30")),
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
            master_api_url=os.getenv("MASTER_API_URL", "http://localhost:8080"),
            cluster_token=os.getenv("CLUSTER_TOKEN", "dev-token"),
            master_request_timeout=float(os.getenv("MASTER_REQUEST_TIMEOUT", "30")),
            tls_verify=os.getenv("TLS_VERIFY", "true").lower() == "true",
            max_retry_same=int(os.getenv("MAX_RETRY_SAME", "3")),
            max_total_retries=int(os.getenv("MAX_TOTAL_RETRIES", "5")),
            read_only=os.getenv("READ_ONLY", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "info"),
        )
