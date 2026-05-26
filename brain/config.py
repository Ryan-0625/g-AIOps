"""Brain configuration — loaded from environment variables with defaults.

Three-layer merge priority (highest wins):
  1. Environment variables
  2. YAML config file (/app/brain.yaml or BRAIN_CONFIG_PATH)
  3. Code defaults (dataclass field defaults)
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)
# YAML to BrainConfig field mapping (nested section.key -> flat field)
_YAML_FIELD_MAP = {
    "llm": {
        "provider": "llm_provider",
        "model": "llm_model",
        "base_url": "llm_base_url",
        "timeout": "llm_timeout",
        "max_retries": "llm_max_retries",
        "context_limit": "llm_context_limit",
    },
    "master": {
        "api_url": "master_api_url",
        "cluster_token": "cluster_token",
        "request_timeout": "master_request_timeout",
    },
    "engine": {
        "max_retry_same_action": "max_retry_same",
        "max_total_retries": "max_total_retries",
        "analyst_model": "analyst_model",
        "planner_model": "planner_model",
    },
    "logging": {
        "level": "log_level",
    },
    "param_filter": {
        "max_str_param_len": "max_str_param_len",
        "max_cmd_length": "max_cmd_length",
    },
}


def _yaml_to_config(data: dict, cfg) -> None:
    for section_key, section_val in data.items():
        if section_key in _YAML_FIELD_MAP and isinstance(section_val, dict):
            mapping = _YAML_FIELD_MAP[section_key]
            for yaml_key, cfg_field in mapping.items():
                if yaml_key in section_val and section_val[yaml_key] is not None:
                    if hasattr(cfg, cfg_field):
                        setattr(cfg, cfg_field, section_val[yaml_key])
        else:
            if hasattr(cfg, section_key) and section_val is not None:
                setattr(cfg, section_key, section_val)





@dataclass
class BrainConfig:
    # LLM
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_base_url: str = "http://localhost:11434"
    llm_timeout: float = 30.0
    llm_max_retries: int = 2
    llm_context_limit: int = 32000

    # Master API
    master_api_url: str = "http://localhost:32080"
    cluster_token: str = "dev-token"
    master_request_timeout: float = 30.0
    tls_verify: bool = True

    # Engine
    max_retry_same: int = 3
    max_total_retries: int = 5

    # Degradation / Read-Only
    analyst_model: str = ""
    planner_model: str = ""
    read_only: bool = False

    # API
    api_rate_limit: int = 30  # max requests per minute per client IP

    # Logging
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "BrainConfig":
        """Load config from environment variables only (legacy).

        Kept for backward compatibility. Prefer load() which also reads YAML.
        """
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
            llm_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            llm_base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            llm_timeout=float(os.getenv("LLM_TIMEOUT", "30")),
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
            master_api_url=os.getenv("MASTER_API_URL", "http://localhost:32080"),
            cluster_token=os.getenv("CLUSTER_TOKEN", "dev-token"),
            master_request_timeout=float(os.getenv("MASTER_REQUEST_TIMEOUT", "30")),
            tls_verify=os.getenv("TLS_VERIFY", "true").lower() == "true",
            max_retry_same=int(os.getenv("MAX_RETRY_SAME", "3")),
            max_total_retries=int(os.getenv("MAX_TOTAL_RETRIES", "5")),
            read_only=os.getenv("READ_ONLY", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "info"),
            api_rate_limit=int(os.getenv("API_RATE_LIMIT", "30")),
        )

    @classmethod
    def load(cls, config_path: str | None = None) -> "BrainConfig":
        """Three-layer merge: code defaults ← YAML ← environment variables.

        Args:
            config_path: Path to YAML config file. Falls back to BRAIN_CONFIG_PATH env var.

        Returns:
            Validated BrainConfig instance.

        Exits process with code 1 on fatal validation errors.
        """
        cfg = cls()

        # Layer 1: YAML file (lowest priority among overrides)
        path = config_path or os.environ.get("BRAIN_CONFIG_PATH")
        if path:
            try:
                with open(path, encoding='utf-8') as f:
                    import yaml as _yaml
                    data = _yaml.safe_load(f)
                if isinstance(data, dict):
                    _yaml_to_config(data, cfg)
            except FileNotFoundError:
                pass  # YAML is optional
            except Exception as e:
                logger.warning("Failed to load config YAML %s: %s", path, e)

        # Layer 2: Environment variables (highest priority — only if set)
        env_overrides = cls._read_env_overrides()
        for field_name, value in env_overrides.items():
            setattr(cfg, field_name, value)

        # Validate before returning.
        cfg.validate()
        return cfg

    @classmethod
    def _read_env_overrides(cls) -> dict:
        """Read only env vars that are explicitly set. Returns field→value dict."""
        overrides: dict = {}

        # String fields
        _str_map = [
            ("LLM_PROVIDER", "llm_provider"),
            ("OLLAMA_MODEL", "llm_model"),
            ("OLLAMA_URL", "llm_base_url"),
            ("MASTER_API_URL", "master_api_url"),
            ("CLUSTER_TOKEN", "cluster_token"),
            ("LOG_LEVEL", "log_level"),
        ]
        for env_key, field_name in _str_map:
            val = os.environ.get(env_key)
            if val is not None:
                overrides[field_name] = val

        # Numeric fields — validate the cast
        _num_map = [
            ("LLM_TIMEOUT", "llm_timeout", float),
            ("LLM_MAX_RETRIES", "llm_max_retries", int),
            ("MASTER_REQUEST_TIMEOUT", "master_request_timeout", float),
            ("MAX_RETRY_SAME", "max_retry_same", int),
            ("MAX_TOTAL_RETRIES", "max_total_retries", int),
            ("API_RATE_LIMIT", "api_rate_limit", int),
        ]
        for env_key, field_name, cast in _num_map:
            val = os.environ.get(env_key)
            if val is not None:
                try:
                    overrides[field_name] = cast(val.strip())
                except (ValueError, TypeError):
                    logger.warning("Invalid %s=%r, using default", env_key, val)

        # Boolean fields
        for env_key, field_name in [("TLS_VERIFY", "tls_verify"), ("READ_ONLY", "read_only")]:
            val = os.environ.get(env_key)
            if val is not None:
                overrides[field_name] = val.strip().lower() == "true"

        return overrides

    def validate(self) -> None:
        """Validate config. Logs warnings and raises ValueError on fatal issues."""
        fatal = False

        # Provider must be recognised.
        if self.llm_provider not in ("ollama", "openai"):
            logger.error("llm_provider=%r not supported (use ollama or openai)", self.llm_provider)
            fatal = True

        # Numeric bounds.
        if self.llm_timeout <= 0:
            logger.error("llm_timeout must be > 0, got %s", self.llm_timeout)
            fatal = True
        if self.master_request_timeout <= 0:
            logger.error("master_request_timeout must be > 0, got %s", self.master_request_timeout)
            fatal = True
        if self.api_rate_limit <= 0:
            logger.error("api_rate_limit must be > 0, got %s", self.api_rate_limit)
            fatal = True
        if self.llm_max_retries < 0:
            logger.error("llm_max_retries must be >= 0, got %s", self.llm_max_retries)
            fatal = True

        # Warn on default dev token.
        if self.cluster_token == "dev-token":
            logger.warning("cluster_token is the dev default — set CLUSTER_TOKEN env var for production")

        if fatal:
            import sys
            sys.exit(1)
