"""Code Generator — LLM 驱动的运维工具代码生成器。

当现有工具库无法满足任务需求时，CodeGenerator 负责:
1. 分析任务目标，确定需要什么工具
2. 调用 LLM 生成工具代码（bash/python3/node）
3. 安全预检（静态分析）
4. 通过 Master 部署到 Worker
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from llm.adapter import LLMAdapter
from logger.structured_logger import get_logger

logger = get_logger()

TOOL_GENERATION_PROMPT = """You are gAIOps Code Generator. Generate a {language} script that performs the following task:

## Task
{task_description}

## Requirements
- Input: Parameters via TOOL_PARAMS environment variable (JSON string)
- Output: Valid JSON to stdout (ONLY JSON, no extra text or debug output)
- Timeout: {timeout} seconds

## Constraints
- NO interactive input
- NO network downloads or external code execution
- NO access to /etc/shadow, /etc/passwd, /root/.ssh/ (blocked by security scanner)
- NO fork bombs or infinite loops
- NO system modification outside /tmp/ and /var/tmp/
- Handle errors gracefully: output {{"status": "error", "error": "description"}}

## Output Format (strict)
Success: {{"status": "ok", "data": {{...key value pairs...}}}}
Error: {{"status": "error", "error": "human readable description"}}

## Example (bash)
```bash
TOOL_PARAMS='{"target": "/tmp"}'
# Parse params
target=$(echo "$TOOL_PARAMS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('target','/'))")
# Do work and output JSON
printf '{"status": "ok", "data": {"path": "%s", "size_bytes": %s}}\\n' "$target" "$(du -sb "$target" 2>/dev/null | cut -f1 || echo 0)"
```

Generate ONLY the script code, no explanations, no markdown formatting around the code."""


@dataclass
class GeneratedTool:
    """生成的工具代码。"""
    action: str
    language: str           # bash | python3 | node
    code: str
    description: str
    risk_level: str         # readonly | write | dangerous
    timeout: int
    params_schema: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class CodeGenerationError(Exception):
    pass


class CodeGenerator:
    """LLM 驱动的工具代码生成器。"""

    def __init__(self, llm: LLMAdapter, max_retries: int = 2):
        self.llm = llm
        self.max_retries = max_retries

    async def generate(
        self,
        task: str,
        language: str = "bash",
        timeout: int = 30,
    ) -> GeneratedTool:
        """生成工具代码。"""
        prompt = TOOL_GENERATION_PROMPT.format(
            language=language,
            task_description=task[:1000],
            timeout=timeout,
        )

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30.0,
                )

                raw_content = ""
                if isinstance(response, dict):
                    raw_content = response.get("message", {}).get("content", "")

                if not raw_content:
                    continue

                code = self._extract_code(raw_content, language)
                if not code:
                    last_error = "Could not extract code from LLM response"
                    continue

                # Auto-generate action name
                action = self._generate_action_name(task)

                # Estimate risk level
                risk = self._estimate_risk(code, language)

                # Security warnings
                warnings = self._scan_security(code)

                return GeneratedTool(
                    action=action,
                    language=language,
                    code=code,
                    description=task[:200],
                    risk_level=risk,
                    timeout=timeout,
                    warnings=warnings,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Code generation attempt {attempt + 1} failed: {e}")

        raise CodeGenerationError(
            f"Failed to generate code after {self.max_retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    def _extract_code(self, text: str, language: str) -> Optional[str]:
        """从 LLM 响应中提取代码块。"""
        # Try markdown code blocks
        # Match bash, sh, python, python3, node, javascript, js
        lang_patterns = [language, "bash", "sh", "python", "python3", "node", "javascript", "js", "shell"]
        for lp in lang_patterns:
            pattern = rf"```(?:{lp})?\s*\n(.*?)```"
            match = re.search(pattern, text, re.DOTALL)
            if match:
                code = match.group(1).strip()
                if code:
                    return code

        # Try to find any code-like content
        if self._looks_like_code(text, language):
            return text.strip()

        return None

    def _looks_like_code(self, text: str, language: str) -> bool:
        """启发式判断文本是否像代码。"""
        text = text.strip()
        code_indicators = [
            "#!/bin/" if language == "bash" else None,
            "import " if language in ("python3", "python") else None,
            "def " if language in ("python3", "python") else None,
            "console.log" if language in ("node", "javascript") else None,
            "function " if language in ("node", "javascript") else None,
            "const " if language in ("node", "javascript") else None,
            "print(" if language == "python3" else None,
        ]
        for indicator in code_indicators:
            if indicator and indicator in text:
                return True
        return False

    def _generate_action_name(self, task: str) -> str:
        """根据任务描述生成 action 名称。"""
        task_lower = task.lower()

        # Pattern matching for common tasks
        mappings = [
            (r"(check|get|show|list)\s+(disk|storage)", "custom.disk_check"),
            (r"(check|get)\s+(memory|mem|cpu|load)", "custom.system_check"),
            (r"(restart|stop|start)\s+(service|nginx|app)", "custom.service_op"),
            (r"(deploy|install|setup)\s+", "custom.deploy"),
            (r"(backup|archive|compress)", "custom.backup"),
            (r"(clean|purge|remove)\s+(temp|log|old)", "custom.cleanup"),
            (r"(ping|check|test)\s+.*(connect|network|reach)", "custom.network_check"),
            (r"(list|show|get)\s+(file|dir|directory|folder)", "custom.file_list"),
            (r"(read|cat|view|show|get)\s+(log|file|config)", "custom.read_file"),
            (r"(health|status|check)", "custom.healthcheck"),
        ]

        for pattern, name in mappings:
            if re.search(pattern, task_lower):
                return name

        # Fallback: hash-based name
        hash_suffix = hashlib.md5(task.encode()).hexdigest()[:8]
        return f"custom.gen_{hash_suffix}"

    def _estimate_risk(self, code: str, language: str) -> str:
        """估算代码的风险等级。"""
        dangerous_patterns = [
            r"rm\s+(-rf?)\s+/", r"mkfs\.", r"dd\s+if=",
            r"/etc/(shadow|passwd|sudoers)", r"chmod\s+777",
            r"kill\s+-9", r"reboot", r"shutdown",
        ]
        write_patterns = [
            r">\s*/", r"mv\s+", r"cp\s+", r"chown", r"chmod",
            r"systemctl\s+(restart|stop|start)",
            r"docker\s+(rm|kill|stop)",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, code):
                return "dangerous"
        for pattern in write_patterns:
            if re.search(pattern, code):
                return "write"
        return "readonly"

    def _scan_security(self, code: str) -> list[str]:
        """安全扫描，返回告警列表。"""
        warnings = []
        scanners = [
            (r"rm\s+(-rf?)\s+/", "Dangerous recursive delete"),
            (r"(curl|wget).*\|.*(bash|sh)", "Command injection via pipe"),
            (r"/(etc/shadow|etc/passwd|root/\.ssh)", "Sensitive file access"),
            (r":\{\s*\|:\s*&\s*\};:", "Fork bomb detected"),
            (r"mkfs\.\w+|dd\s+if=.*of=/dev/", "Disk format operation"),
            (r"(stratum|xmrig|cryptonight|minerd)", "Crypto miner detected"),
        ]
        for pattern, message in scanners:
            if re.search(pattern, code):
                warnings.append(message)
        return warnings
