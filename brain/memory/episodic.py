"""Episodic Memory — 情景记忆，记录历史执行轨迹。

每个 session 的执行步骤、成功/失败模式、错误上下文都会存入情景记忆。
后续 session 可通过相似度检索找到历史模式，避免重复犯错。

存储策略:
- 内存存储（开发期），上限 1000 条
- 按 action + error_code 精确匹配检索
- 后续可升级为 embedding 向量相似度检索
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Episode:
    """一条执行记录。"""
    trace_id: str
    context_hash: str             # 上下文特征哈希
    action: str
    params: dict[str, Any]
    status: str                   # "success" | "failure"
    error_code: Optional[str]
    error_message: Optional[str]
    summary: str                  # LLM 生成的一句话摘要
    duration_ms: int
    timestamp: int = 0
    react_steps: int = 0          # v2.0: ReAct 循环步数


class EpisodicMemory:
    """情景记忆存储。"""

    def __init__(self, max_episodes: int = 1000):
        self.episodes: list[Episode] = []
        self.max_episodes = max_episodes

    async def store(self, episode: Episode) -> None:
        """存储一条执行记录。超过上限时淘汰最旧记录。"""
        self.episodes.append(episode)
        if len(self.episodes) > self.max_episodes:
            self.episodes.pop(0)

    async def retrieve_similar(
        self,
        action: str,
        error_code: Optional[str] = None,
        top_k: int = 3,
    ) -> list[Episode]:
        """检索相似历史执行记录。

        简易实现: 按 action 精确匹配 + error_code 过滤。
        后续可升级为 embedding 相似度检索。
        """
        candidates = [e for e in self.episodes if e.action == action]
        if error_code:
            candidates = [e for e in candidates if e.error_code == error_code]
        return candidates[-top_k:]  # 返回最近的 top_k

    async def retrieve_by_context(
        self, context_hash: str, top_k: int = 3
    ) -> list[Episode]:
        """检索相似上下文的执行记录。"""
        candidates = [e for e in self.episodes if e.context_hash == context_hash]
        return candidates[-top_k:]

    def stats(self) -> dict[str, int]:
        """记忆统计。"""
        return {
            "total_episodes": len(self.episodes),
            "success_count": sum(1 for e in self.episodes if e.status == "success"),
            "failure_count": sum(1 for e in self.episodes if e.status == "failure"),
        }
