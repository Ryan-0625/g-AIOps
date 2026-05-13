"""Zero-cost intent classifier — keyword/pattern matching, no LLM inference.

Categories:
  IRRELEVANT — greetings, jokes, chit-chat → rejected immediately
  HEALTH     — cluster health/status queries → fast-path via MasterClient
  WORKERS    — worker list/capability queries → fast-path via MasterClient
  TOOL       — single-tool operations (ping, disk, dns, etc.) → fast-path via MasterClient
  COMPLEX    — multi-step reasoning (restart, troubleshoot, etc.) → LLM pipeline
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentCategory(Enum):
    IRRELEVANT = "irrelevant"
    HEALTH = "health"
    WORKERS = "workers"
    TOOL = "tool"
    COMPLEX = "complex"


@dataclass
class IntentResult:
    category: IntentCategory
    tool_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


# ── Tool name constants ──────────────────────────────────────────────

TOOL_PING = "ping.icmp"
TOOL_DISK = "disk.usage"
TOOL_SERVICE_STATUS = "service.status"
TOOL_PROCESS_LIST = "process.list"
TOOL_LOG_TAIL = "log.tail"
TOOL_SYSTEM_INFO = "system.info"
TOOL_DNS = "dns.lookup"
TOOL_HTTP_GET = "http.get"
TOOL_CONTAINER = "container.list"
TOOL_NETWORK = "network.connections"


class IntentClassifier:
    """Stateless regex-based intent classifier.

    Thread-safe. Pure Python stdlib — zero external dependencies.
    """

    # ── Irrelevant patterns (rejected immediately) ──────────────────
    IRRELEVANT = [
        re.compile(p) for p in [
            r"^(hi|hello|hey|good\s*(morning|afternoon|evening)|yo)\b",
            r"^(你好|您好|嗨|嘿|哈喽|大家好)",
            r"^(早上好|下午好|晚上好|晚安)",
            r"^(thanks|thank\s*you|thx|ty)\b",
            r"^(谢谢|感谢|多谢|辛苦了)",
            r"^(bye|goodbye|see\s*you|later|cya)\b",
            r"^(再见|拜拜|明天见|回头见)",
            r"(how are you|how's it going|what'?s up|sup)",
            r"(你好吗|怎么样|最近怎样|在吗)",
            r"(what is your name|who are you|tell me about yourself|introduce yourself)",
            r"(你是谁|你叫什么|介绍你自己|自我介绍一下|怎么称呼你)",
            r"(tell me a joke|tell us a joke|make me laugh)",
            r"(joke|funny|lol|lmao|rofl|haha|laugh)",
            r"(write a poem|write a story|compose|create a story)",
            r"(weather|stock price|news about|what'?s happening)",
            r"(opinion on|thoughts? about|feel about)",
            r"^(what do you think about)",
            # Chinese irrelevant — general knowledge, news, opinions
            r"(什么是|什么是|怎么样才)",
            r"(你觉得|你认为|你怎么看|如何看待)",
            r"(中美|中国|美国|政治|经济|历史|文化)",
            r"(股票|天气|新闻|体育|娱乐|电影|音乐)",
            r"(写[一篇首]|创作|编[一个])",
            r"(讲个笑话|说个笑话|来个笑话)",
        ]
    ]

    # ── Health check patterns ───────────────────────────────────────
    HEALTH = [
        re.compile(p) for p in [
            r"(health|status|cluster\s*status)",
            r"is (everything|the (cluster|system|master))\s*(ok|healthy|running|up|alive)",
            r"(how|how'?s)\s+(is|are)\s+(things|everything|the\s*system|the\s*cluster)",
            r"^health\s*$",
            r"^status\s*$",
            r"(ping|check)\s*(master|cluster)",
        ]
    ]

    # ── Worker query patterns ───────────────────────────────────────
    WORKERS = [
        re.compile(p) for p in [
            r"(list|show|get|view|display).*(worker|agent|node)",
            r"(worker|agent|node)s?\s*(list|available|connected|online|status)",
            r"(how many).*(worker|agent|node)",
            r"(what|which)\s+(workers|agents|nodes).*(available|exist|connected)",
            r"(what|which)\s+(tools|actions|capabilities).*(available|exist)",
            r"^workers?\s*$",
            r"^nodes?\s*$",
        ]
    ]

    # ── Tool execution patterns: (regex, tool_name, [(param_key, group_idx), ...]) ──
    TOOL_PATTERNS: list[tuple[re.Pattern, str, list[tuple[str, int]]]] = [
        (
            re.compile(r"(?:ping|check\s+(?:reachability|connectivity))\s+([\w.-]+)(?:\s+(\d+)\s*times?)?", re.IGNORECASE),
            TOOL_PING, [("target", 1), ("count", 2)],
        ),
        (
            re.compile(r"(?:check|show|get)\s+disk\s*(?:usage|space|free)?\s*(?:for\s+([/\w]+))?", re.IGNORECASE),
            TOOL_DISK, [("path", 1)],
        ),
        (
            re.compile(r"(?:check|what'?s?|is)\s+(\S+)\s+(?:status|running|working|up|alive|down)", re.IGNORECASE),
            TOOL_SERVICE_STATUS, [("name", 1)],
        ),
        (
            re.compile(r"(?:service|svc)\s+(?:status\s+)?(\S+)", re.IGNORECASE),
            TOOL_SERVICE_STATUS, [("name", 1)],
        ),
        (
            re.compile(r"(?:list|show)\s+(process|running|ps)", re.IGNORECASE),
            TOOL_PROCESS_LIST, [],
        ),
        (
            re.compile(r"(?:log|tail|recent\s*logs|show\s*logs)", re.IGNORECASE),
            TOOL_LOG_TAIL, [],
        ),
        (
            re.compile(r"(?:dns|resolve|lookup)\s+([\w.-]+)", re.IGNORECASE),
            TOOL_DNS, [("hostname", 1)],
        ),
        (
            re.compile(r"(?:http.?get|fetch|check\s+url|check\s+website|curl)\s+(\S+)", re.IGNORECASE),
            TOOL_HTTP_GET, [("url", 1)],
        ),
        (
            re.compile(r"(?:system\s+(?:info|information)|sysinfo|machine\s*info|os\s*version|check\s+(?:system|machine|os)\s*$|show\s+(?:system|machine))", re.IGNORECASE),
            TOOL_SYSTEM_INFO, [],
        ),
        (
            re.compile(r"(?:container|docker)\s*(?:list|ps|running)?", re.IGNORECASE),
            TOOL_CONTAINER, [],
        ),
        (
            re.compile(r"(?:network|netstat|connections?|ports?)\s*(?:connections?|status|active)?", re.IGNORECASE),
            TOOL_NETWORK, [],
        ),
        (
            re.compile(r"^(?:disk|storage|space|usage)\s*$", re.IGNORECASE),
            TOOL_DISK, [],
        ),
        # Generic "check <name>" — keep last to avoid stealing from specific patterns.
        (
            re.compile(r"^(?:status|check|show)\s+(?:of\s+)?(\S+)", re.IGNORECASE),
            TOOL_SERVICE_STATUS, [("name", 1)],
        ),
    ]

    # ── Complex task indicators (skip fast-path, go to LLM) ─────────
    COMPLEX = [
        re.compile(p) for p in [
            r"(restart|reboot|shutdown|stop|kill|delete|remove|destroy)",
            r"(troubleshoot|debug|investigate|diagnose|fix|repair|resolve|analyze)",
            r"(deploy|install|setup|configure|update|upgrade|patch|backup|restore)",
            r"(create|write|modify|edit|change)\s+(file|config|script)",
            r"health.?check.*(fix|restart|repair|investigate)",
            r"(maintenance|maintain|migrate|transfer)",
            r"because|since|due to|reason for",
            r"(then|after that|afterwards)\s+(check|run|do|execute|verify)",
            r"(compare|contrast|investigate|why (is|did|are|was))",
        ]
    ]

    # ── Language detection ──────────────────────────────────────────

    _ZH_PAT = re.compile(r'[一-鿿　-〿＀-￯]')

    @staticmethod
    def _detect_lang(text: str) -> str:
        """Detect 'zh' or 'en' based on presence of CJK characters."""
        return "zh" if IntentClassifier._ZH_PAT.search(text) else "en"

    # ── Greeting responses ───────────────────────────────────────────

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

    # ── Public API ──────────────────────────────────────────────────

    def classify(self, text: str) -> IntentResult:
        """Classify user intent using regex pattern matching (zero LLM cost).

        Returns an IntentResult with the matched category and extracted data.
        """
        stripped = text.strip()
        if not stripped:
            return IntentResult(
                category=IntentCategory.COMPLEX,
                reason="Empty message.",
            )

        # 1. Check irrelevant (fast reject)
        for pat in self.IRRELEVANT:
            if pat.search(stripped):
                lang = self._detect_lang(stripped)
                greeting = self._GREETING_ZH if lang == "zh" else self._GREETING_EN
                return IntentResult(
                    category=IntentCategory.IRRELEVANT,
                    reason=greeting,
                )

        # 2. Check health
        for pat in self.HEALTH:
            if pat.search(stripped):
                return IntentResult(category=IntentCategory.HEALTH)

        # 3. Check workers
        for pat in self.WORKERS:
            if pat.search(stripped):
                return IntentResult(category=IntentCategory.WORKERS)

        # 4. Check complex — must go to LLM
        for pat in self.COMPLEX:
            if pat.search(stripped):
                return IntentResult(
                    category=IntentCategory.COMPLEX,
                    reason="Complex operation detected — requires LLM reasoning.",
                )

        # 5. Check simple tool execution
        for pat, tool_name, param_spec in self.TOOL_PATTERNS:
            m = pat.search(stripped)
            if m:
                params: dict[str, Any] = {}
                for key, group_idx in param_spec:
                    val = m.group(group_idx)
                    if val is not None and val.strip():
                        raw = val.strip()
                        # Convert count to int
                        if key == "count":
                            try:
                                params[key] = int(raw)
                            except ValueError:
                                params[key] = raw
                        else:
                            params[key] = raw

                # Additional param extraction for specific tools
                if tool_name == TOOL_PING:
                    count_m = re.search(r"(\d+)\s*(time|packet)", stripped, re.IGNORECASE)
                    if count_m:
                        params["count"] = int(count_m.group(1))
                    if "target" not in params:
                        # Try to extract any hostname-like target
                        host_m = re.search(r"(?:ping|check)\s+([\w.-]+)", stripped, re.IGNORECASE)
                        if host_m:
                            params["target"] = host_m.group(1)

                if tool_name == TOOL_DNS and "hostname" in params:
                    # Check for record type (A, AAAA, MX, TXT, CNAME)
                    rt_m = re.search(r"\s+(A|AAAA|MX|TXT|CNAME)\s*$", stripped, re.IGNORECASE)
                    if rt_m:
                        params["record_type"] = rt_m.group(1).upper()

                return IntentResult(
                    category=IntentCategory.TOOL,
                    tool_name=tool_name,
                    params=params,
                )

        # 6. Default to complex (LLM handles it)
        return IntentResult(
            category=IntentCategory.COMPLEX,
            reason="Could not classify with fast path — delegating to LLM.",
        )
