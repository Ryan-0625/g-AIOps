"""Semantic Memory — 语义记忆/运维知识库。

存储:
- 工具用法模式（什么场景用什么工具、参数模式）
- 已知修复策略（特定错误码的最佳处理方式）
- 部署模式（什么工具代码适合什么任务）

知识来源:
- predefined: 预置种子知识
- learned: 从成功经验自动学习
- human: 人工注入
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import time


@dataclass
class KnowledgeEntry:
    """一条运维知识。"""
    topic: str                  # 主题标签
    pattern: str                # 匹配模式（action:error_code 格式）
    solution: str               # 解决策略描述
    confidence: float = 0.5     # 置信度 [0, 1]
    source: str = "predefined"  # predefined | learned | human
    created_at: int = 0
    last_used: int = 0
    use_count: int = 0


class SemanticMemory:
    """语义记忆 — 运维知识库。"""

    def __init__(self):
        # 预置种子知识
        self.entries: list[KnowledgeEntry] = [
            KnowledgeEntry(
                topic="disk_full",
                pattern="disk.usage:usage_pct>90",
                solution="execute disk.cleanup or exec.run with cleanup script to free disk space",
                confidence=0.9, source="predefined",
            ),
            KnowledgeEntry(
                topic="service_down",
                pattern="service.status:status=inactive",
                solution="execute service.restart, then verify with service.status, escalate if still inactive",
                confidence=0.8, source="predefined",
            ),
            KnowledgeEntry(
                topic="tool_not_found",
                pattern="NO_AVAILABLE_WORKER:*",
                solution="check Deployer templates; if exists deploy; else ask CodeGenerator to create the tool",
                confidence=0.7, source="predefined",
            ),
            KnowledgeEntry(
                topic="ping_failed",
                pattern="PING_FAILED:*",
                solution="check if target is reachable via DNS first (dns.lookup), then try a different target",
                confidence=0.8, source="predefined",
            ),
            KnowledgeEntry(
                topic="compile_error",
                pattern="TOOL_COMPILE_ERROR:*",
                solution="fix syntax error in generated code and re-deploy; common issues: missing shebang, unclosed quotes",
                confidence=0.6, source="predefined",
            ),
            KnowledgeEntry(
                topic="deploy_timeout",
                pattern="TOOL_DEPLOY_TIMEOUT:*",
                solution="retry deployment; if persistent, check Worker connectivity and reduce code size",
                confidence=0.7, source="predefined",
            ),
        ]

    async def query(
        self,
        action: str,
        error_code: Optional[str],
        context: str = "",
    ) -> Optional[KnowledgeEntry]:
        """根据当前执行上下文检索相关知识。"""
        # 精确匹配: action:error_code
        if error_code:
            exact_pattern = f"{action}:{error_code}"
            for entry in self.entries:
                if entry.pattern == exact_pattern:
                    entry.last_used = int(time.time())
                    entry.use_count += 1
                    return entry

        # 模糊匹配: action:*
        wildcard_pattern = f"{action}:*"
        for entry in self.entries:
            if entry.pattern == wildcard_pattern:
                entry.last_used = int(time.time())
                entry.use_count += 1
                return entry

        # 全局匹配: *:error_code
        if error_code:
            for entry in self.entries:
                if entry.pattern.endswith(f":{error_code}") or entry.pattern.endswith(":*"):
                    return entry

        return None

    async def learn(self, entry: KnowledgeEntry) -> None:
        """从成功经验中学习新知识。"""
        # 去重：相同 pattern 的更新置信度
        for existing in self.entries:
            if existing.pattern == entry.pattern:
                # 提升置信度，但不超过 1.0
                existing.confidence = min(1.0, existing.confidence + 0.1)
                existing.solution = entry.solution
                existing.source = "learned"
                return
        self.entries.append(entry)

    async def search(self, query: str) -> list[KnowledgeEntry]:
        """全文搜索知识库。"""
        query_lower = query.lower()
        results = []
        for entry in self.entries:
            if (query_lower in entry.topic.lower()
                    or query_lower in entry.pattern.lower()
                    or query_lower in entry.solution.lower()):
                results.append(entry)
        return results[:5]

    def stats(self) -> dict:
        return {
            "total_entries": len(self.entries),
            "by_source": {
                "predefined": sum(1 for e in self.entries if e.source == "predefined"),
                "learned": sum(1 for e in self.entries if e.source == "learned"),
                "human": sum(1 for e in self.entries if e.source == "human"),
            },
        }
