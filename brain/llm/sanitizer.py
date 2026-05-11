"""LLM output three-layer sanitizer: JSON repair → schema validate → param sanitize."""

import json
import re
from typing import Any

from logger.structured_logger import get_logger

logger = get_logger()

SHELL_META_RE = re.compile(r'[;&|`$()]')
PATH_TRAVERSAL_RE = re.compile(r'(\.\./|\.\.\\)')
COMMAND_CHAIN_RE = re.compile(r'(curl|wget|nc)\s+.*?(\||;|`|\$\()', re.IGNORECASE)
SENSITIVE_PATHS = [
    "/etc/shadow", "/etc/passwd", "/etc/kubernetes/",
    "/root/.ssh/", "/var/lib/kubelet/",
]


class ParamSanitizationError(ValueError):
    pass


class SanitizedOutput:
    def __init__(
        self,
        action: str | None = None,
        params: dict[str, Any] | None = None,
        error: str | None = None,
        truncated: bool = False,
    ):
        self.action = action
        self.params = params or {}
        self.error = error
        self.truncated = truncated


class LLMOutputSanitizer:
    """Three-layer sanitizer for LLM tool call output.

    Layer 1: Repair broken JSON (missing quotes, trailing commas).
    Layer 2: Validate action exists and required params are present.
    Layer 3: Sanitize parameters (shell injection, path traversal, length).
    """

    def __init__(self, tool_registry: dict[str, dict[str, Any]]):
        self.tool_registry = tool_registry

    def sanitize_tool_call(self, raw: str) -> SanitizedOutput:
        if not raw or not raw.strip():
            return SanitizedOutput(error="EMPTY_OUTPUT")

        # Layer 1: JSON repair
        parsed = self._try_fix_json(raw.strip())
        if parsed is None:
            return SanitizedOutput(error=f"INVALID_JSON: {raw[:200]}")

        action = parsed.get("action") or parsed.get("name") or parsed.get("function", "")
        params = parsed.get("params") or parsed.get("arguments") or {}

        # Layer 2: Schema validation
        if action not in self.tool_registry:
            return SanitizedOutput(
                error=f"UNKNOWN_TOOL: {action}",
                params={"original": raw[:200]},
            )

        schema = self.tool_registry[action]
        required = schema.get("required_params", [])
        missing = [f for f in required if f not in params or params[f] is None]
        if missing:
            return SanitizedOutput(
                error=f"MISSING_PARAMS: {', '.join(missing)}",
                params={"original": raw[:200]},
            )

        # Layer 3: Parameter sanitization
        try:
            sanitized_params = self._sanitize_params(action, params)
        except ParamSanitizationError as e:
            return SanitizedOutput(error=f"PARAM_SANITIZED: {e}")

        return SanitizedOutput(action=action, params=sanitized_params)

    def _try_fix_json(self, raw: str) -> dict[str, Any] | None:
        """Attempt to parse and repair common JSON issues."""
        # Direct parse.
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Fix common issues: trailing comma, missing quotes on keys.
        raw = re.sub(r',\s*}', '}', raw)
        raw = re.sub(r',\s*]', ']', raw)
        raw = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r'"\1":', raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _sanitize_params(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Sanitize each parameter. Raises ParamSanitizationError on rejection."""
        result: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str):
                # Shell metacharacter detection.
                if SHELL_META_RE.search(value):
                    raise ParamSanitizationError(
                        f"param '{key}' contains shell metacharacters"
                    )

                # Command chain detection.
                if COMMAND_CHAIN_RE.search(value):
                    raise ParamSanitizationError(
                        f"param '{key}' looks like a command chain"
                    )

                # Path traversal for path-like params.
                if key in ("path", "command", "target", "name"):
                    if PATH_TRAVERSAL_RE.search(value):
                        raise ParamSanitizationError(
                            f"param '{key}' contains path traversal"
                        )
                    for sensitive in SENSITIVE_PATHS:
                        if sensitive in value:
                            raise ParamSanitizationError(
                                f"param '{key}' references sensitive path: {sensitive}"
                            )

                # Length limit.
                max_len = 1024
                if key in ("command", "args"):
                    max_len = 512
                if len(value) > max_len:
                    logger.warning(
                        "param truncated",
                        extra={"data": {"key": key, "original_len": len(value), "max_len": max_len}},
                    )
                    value = value[:max_len]
                    result["_truncated"] = True

            result[key] = value
        return result
