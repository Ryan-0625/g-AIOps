"""LLM-based intent router — replaces regex classifier for intent classification.

Uses a single non-streaming LLM call to classify user intent into 4 categories:
  GREETING     — greetings, self-introduction → fixed bilingual response
  IRRELEVANT   — jokes, general knowledge, chit-chat → fixed "cannot answer"
  TOOL         — single-tool operation → fast-path via master.execute()
  TROUBLESHOOT — multi-step reasoning → full GraphEngine pipeline

Fallback: if LLM is unavailable, delegates to regex IntentClassifier.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from llm.adapter import LLMAdapter
from tools.tool_registry import REGISTRY
from intent.classifier import IntentClassifier, IntentResult, IntentCategory

# ── Fixed bilingual responses ─────────────────────────────────────────

_GREETING_EN = (
    "Hello! I am gAIOps Brain, your AI operations assistant. "
    "I can help you check cluster health, run diagnostic tools, "
    "execute system commands, and more. How can I assist you today?"
)
_GREETING_ZH = (
    "你好！我是 gAIOps Brain，你的 AI 运维助手。"
    "我可以帮你检查集群状态、执行诊断工具、"
    "运行系统命令等。请问有什么可以帮你的？"
)

_IRRELEVANT_EN = (
    "Sorry, I cannot answer that question. I am an AI operations assistant "
    "focused on cluster management and system diagnostics."
)
_IRRELEVANT_ZH = (
    "抱歉，我无法回答这个问题。我是一个 AI 运维助手，"
    "专注于集群管理和系统诊断。"
)

# ── CJK detection ────────────────────────────────────────────────────

_ZH_PAT = re.compile(r"[一-鿿　-〿＀-￯]")


def _detect_lang(text: str) -> str:
    """Detect 'zh' or 'en' based on presence of CJK characters."""
    return "zh" if _ZH_PAT.search(text) else "en"


# ── Tool description helper ──────────────────────────────────────────

_VIRTUAL_TOOLS = [
    ("_health_check", "Check cluster health and status. No parameters."),
    ("_list_workers", "List connected workers and their capabilities. No parameters."),
]


def _build_tool_descriptions() -> str:
    lines = []
    for name, info in REGISTRY.items():
        params_desc = "; ".join(
            f"{k}: {v.get('description', '')}"
            for k, v in info.get("params", {}).items()
        ) or "none"
        lines.append(f'  - "{name}": {info["description"]} (params: {params_desc})')
    for name, desc in _VIRTUAL_TOOLS:
        lines.append(f'  - "{name}": {desc}')
    return "\n".join(lines)


# ── Category enum ────────────────────────────────────────────────────


class RouterCategory(Enum):
    GREETING = "greeting"
    IRRELEVANT = "irrelevant"
    TOOL = "tool"
    TROUBLESHOOT = "troubleshoot"


# ── Result dataclass ─────────────────────────────────────────────────


@dataclass
class RouterResult:
    category: RouterCategory
    tool_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    lang: str = "en"


# ── Router class ─────────────────────────────────────────────────────


class Router:
    """LLM-based intent router.

    Thread-safe. Uses LLMAdapter.chat() for single-shot classification.
    Falls back to regex IntentClassifier if the LLM is unavailable.
    """

    SYSTEM_PROMPT = (
        "You are gAIOps Brain's intent router. Your task is to classify user messages "
        "into exactly one of four categories and return a JSON object.\n\n"
        "## Categories\n\n"
        '1. "greeting" — User is greeting, introducing themselves, or asking who you are. '
        "Examples: hello, hi, 你好, who are you, what can you do, good morning.\n"
        '2. "irrelevant" — User asks something outside operations/systems scope. '
        "Examples: tell me a joke, write a poem, what is the weather, "
        "what do you think about politics, news, sports, entertainment, stock prices, "
        "general knowledge questions, opinions, creative writing requests.\n"
        '3. "tool" — User wants to perform a specific operation or check something. '
        "Examples: ping a host, check disk, list workers, show health, "
        "check service status, look up DNS, check system info. "
        "Must identify the exact tool_name from the available tools list below.\n"
        '4. "troubleshoot" — Multi-step reasoning, debugging, repairs, or anything '
        "requiring multiple operations. "
        "Examples: server is slow, investigate why, restart then check, "
        "fix the problem, deploy, configure, troubleshoot network, "
        "analyze logs and fix, why is this happening.\n\n"
        "## Available Tools\n"
        "{tool_descriptions}\n\n"
        "## Language\n"
        "Detect the user's language. Set the 'lang' field to 'zh' for Chinese, 'en' for English. "
        "The 'reason' field should be a brief explanation in the user's detected language.\n\n"
        "## Output Format\n"
        "Respond with ONLY a valid JSON object (no markdown, no code fences):\n"
        '{{\n'
        '  "category": "greeting|irrelevant|tool|troubleshoot",\n'
        '  "tool_name": "exact tool name from the list or empty string",\n'
        '  "params": {{}},\n'
        '  "reason": "brief explanation in user language",\n'
        '  "lang": "zh|en"\n'
        '}}\n\n'
        "Rules:\n"
        "- For 'greeting': tool_name must be empty, params must be empty.\n"
        "- For 'irrelevant': tool_name must be empty, params must be empty.\n"
        "- For 'tool': tool_name MUST be one of the exact tool names listed above (including virtual tools like _health_check, _list_workers). "
        "Extract relevant parameters from the user message and put them in 'params'.\n"
        "- For 'troubleshoot': tool_name must be empty, params must be empty.\n"
        "- If unsure, default to 'troubleshoot'.\n"
        "- Return ONLY the JSON object, nothing else."
    )

    def __init__(self, llm: LLMAdapter):
        self._llm = llm
        self._fallback = IntentClassifier()
        self._tool_descriptions = _build_tool_descriptions()

    async def route(self, text: str) -> RouterResult:
        """Classify intent via LLM. Falls back to regex classifier on failure."""
        stripped = text.strip()
        if not stripped:
            return RouterResult(
                category=RouterCategory.TROUBLESHOOT,
                reason="Empty message.",
            )

        # Try LLM-based routing.
        try:
            return await self._route_llm(stripped)
        except Exception:
            # Fallback to regex classifier.
            return self._route_fallback(stripped)

    async def _route_llm(self, text: str) -> RouterResult:
        """Call LLM for intent classification."""
        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT.format(
                    tool_descriptions=self._tool_descriptions
                ),
            },
            {"role": "user", "content": text},
        ]

        response = await self._llm.chat(messages=messages, timeout=15.0)
        return self._parse_response(response, text)

    def _parse_response(self, response: dict[str, Any], original_text: str) -> RouterResult:
        """Parse LLM JSON response into RouterResult."""
        try:
            content = ""
            if isinstance(response, dict):
                message = response.get("message", {})
                if isinstance(message, dict):
                    content = message.get("content", "")

            if not content:
                content = str(response)

            # Try to extract JSON from the response (handle code fences).
            json_str = content.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            data = json.loads(json_str)

            category_str = data.get("category", "troubleshoot")
            try:
                category = RouterCategory(category_str)
            except ValueError:
                category = RouterCategory.TROUBLESHOOT

            lang = data.get("lang", _detect_lang(original_text))
            if lang not in ("zh", "en"):
                lang = _detect_lang(original_text)

            tool_name = data.get("tool_name") or None
            params = data.get("params") or {}
            reason = data.get("reason") or None

            # Generate fixed response reason for greeting/irrelevant.
            if category == RouterCategory.GREETING:
                reason = _GREETING_ZH if lang == "zh" else _GREETING_EN
            elif category == RouterCategory.IRRELEVANT:
                reason = _IRRELEVANT_ZH if lang == "zh" else _IRRELEVANT_EN

            return RouterResult(
                category=category,
                tool_name=tool_name,
                params=params,
                reason=reason,
                lang=lang,
            )

        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            # Malformed response — fall through to fallback.
            raise

    def _route_fallback(self, text: str) -> RouterResult:
        """Fallback to regex IntentClassifier."""
        intent: IntentResult = self._fallback.classify(text)
        lang = _detect_lang(text)

        # Map IntentCategory → RouterCategory
        mapping = {
            IntentCategory.IRRELEVANT: RouterCategory.IRRELEVANT,
            IntentCategory.HEALTH: RouterCategory.TOOL,
            IntentCategory.WORKERS: RouterCategory.TOOL,
            IntentCategory.TOOL: RouterCategory.TOOL,
            IntentCategory.COMPLEX: RouterCategory.TROUBLESHOOT,
        }
        category = mapping.get(intent.category, RouterCategory.TROUBLESHOOT)

        # For IRRELEVANT, check if it's actually a greeting.
        if category == RouterCategory.IRRELEVANT:
            if any(
                p.search(text)
                for p in [
                    re.compile(r"^(hi|hello|hey|你好|您好|嗨)\b", re.IGNORECASE),
                    re.compile(r"(who are you|what is your name|你是谁|你叫什么)", re.IGNORECASE),
                    re.compile(r"(what can you do|你能做什么|你有什么用)", re.IGNORECASE),
                ]
            ):
                category = RouterCategory.GREETING
                reason = _GREETING_ZH if lang == "zh" else _GREETING_EN
            else:
                reason = _IRRELEVANT_ZH if lang == "zh" else _IRRELEVANT_EN
            return RouterResult(
                category=category,
                reason=reason,
                lang=lang,
            )

        if category in (RouterCategory.TROUBLESHOOT, RouterCategory.TOOL):
            return RouterResult(
                category=category,
                tool_name=intent.tool_name if category == RouterCategory.TOOL else None,
                params=intent.params if category == RouterCategory.TOOL else {},
                reason=intent.reason,
                lang=lang,
            )

        return RouterResult(
            category=category,
            reason=intent.reason,
            lang=lang,
        )
