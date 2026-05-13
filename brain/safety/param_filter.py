"""ParamFilter — sanitizes Brain→Master instruction parameters.

This is the Brain-side defense layer. Worker has its own (white-list, path
sanitization). ParamFilter catches injection at the source before it ever
reaches the network.

Key checks:
- Shell metacharacters (; | & ` $())
- Command chain patterns (curl | bash)
- Path traversal (../)
- Sensitive paths (/etc/shadow, /root/.ssh/)
- Parameter length limits (aligned with Worker's truncation thresholds)
"""

import re
from dataclasses import dataclass, field
from typing import Any

from logger.structured_logger import get_logger

logger = get_logger()

SHELL_META_RE = re.compile(r'[;&|`$()]')
COMMAND_CHAIN_RE = re.compile(
    r'(curl|wget|nc|fetch)\s+.*?(\||;|`|\$\()', re.IGNORECASE
)
PATH_TRAVERSAL_RE = re.compile(r'(\.\./|\.\.\\)')
SENSITIVE_PATHS = [
    "/etc/shadow", "/etc/passwd", "/etc/kubernetes/",
    "/root/.ssh/", "/var/lib/kubelet/",
]

MAX_STR_PARAM = 1024
MAX_CMD_LENGTH = 512
MAX_LIST_PARAM = 100


@dataclass
class FilterResult:
    passed: bool = False
    sanitized_params: dict[str, Any] = field(default_factory=dict)
    rejected: bool = False
    reason: str = ""
    truncated: bool = False
    original_size: int = 0


class ParamFilter:
    def __init__(self) -> None:
        self.stats = {"blocked": 0, "passed": 0, "truncated": 0}

    def filter(self, action: str, params: dict[str, Any]) -> FilterResult:
        result = FilterResult(passed=False, sanitized_params=dict(params))

        for key, value in params.items():
            if isinstance(value, str):
                check = self._check_string(action, key, value)
                if check["rejected"]:
                    self.stats["blocked"] += 1
                    return FilterResult(
                        passed=False,
                        rejected=True,
                        reason=f"param '{key}' rejected: {check['reason']}",
                    )
                if check.get("truncated"):
                    result.truncated = True
                    result.original_size = check["original_size"]
                result.sanitized_params[key] = check["value"]

            elif isinstance(value, list):
                if len(value) > MAX_LIST_PARAM:
                    result.truncated = True
                    result.sanitized_params[key] = value[:MAX_LIST_PARAM]

        result.passed = True
        self.stats["passed"] += 1
        return result

    def _check_string(self, action: str, key: str, value: str) -> dict[str, Any]:
        max_len = MAX_CMD_LENGTH if key in ("command", "args") else MAX_STR_PARAM
        original_size = len(value)
        truncated = original_size > max_len
        value = value[:max_len]

        if action in ("tool.create",) and key in ("script", "command"):
            pass
        elif SHELL_META_RE.search(value):
            return {"rejected": True, "reason": "shell metacharacters detected"}
        if action in ("tool.create",) and key in ("script", "command"):
            pass
        elif COMMAND_CHAIN_RE.search(value):
            return {"rejected": True, "reason": "command chain pattern detected"}
        if PATH_TRAVERSAL_RE.search(value):
            return {"rejected": True, "reason": "path traversal detected"}
        for sensitive in SENSITIVE_PATHS:
            if sensitive in value:
                return {"rejected": True, "reason": f"access to sensitive path: {sensitive}"}

        return {
            "rejected": False,
            "value": value,
            "truncated": truncated,
            "original_size": original_size if truncated else 0,
        }
