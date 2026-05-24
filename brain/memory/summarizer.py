"""Memory Summarizer — 记忆压缩与检索增强。

将历史轨迹和记忆压缩为结构化摘要供 LLM 使用。
"""

from typing import Any, Optional

from memory.episodic import Episode
from memory.semantic import KnowledgeEntry
from memory.working import WorkingMemory


class MemorySummarizer:
    """记忆压缩器 — 将历史轨迹和记忆压缩为 LLM 友好的提示文本。"""

    def __init__(self):
        pass

    def summarize_trajectory(self, trajectory: list[dict]) -> str:
        """将 ReAct 轨迹压缩为摘要。"""
        if not trajectory:
            return ""

        steps = len(trajectory)
        success = sum(
            1 for t in trajectory
            if isinstance(t.get("observation"), dict)
            and t["observation"].get("status") == "success"
        )
        failures = steps - success

        failed_actions = set()
        for t in trajectory:
            obs = t.get("observation", {})
            if isinstance(obs, dict) and obs.get("status") == "failure":
                ec = obs.get("error", {}).get("code", "UNKNOWN")
                action = t.get("action", "?")
                failed_actions.add(f"{action}[{ec}]")

        parts = [f"ReAct({steps}步, {success}成功/{failures}失败)"]
        if failed_actions:
            parts.append(f"失败: {', '.join(failed_actions)}")
        return " | ".join(parts)

    def build_memory_prompt(
        self,
        episodic: list[Episode],
        semantic: Optional[KnowledgeEntry],
        working: WorkingMemory,
    ) -> str:
        """构建记忆增强提示。"""
        lines = ["[Memory Context]"]

        # 语义记忆
        if semantic:
            lines.append(f"Known pattern: {semantic.pattern}")
            lines.append(f"Suggested: {semantic.solution[:200]}")

        # 情景记忆
        if episodic:
            lines.append("Similar past episodes:")
            for ep in episodic[-3:]:
                icon = "✓" if ep.status == "success" else "✗"
                lines.append(f"  [{icon}] {ep.action}: {ep.summary[:150]}")

        # 工作记忆轨迹
        if working and working.react_trajectory:
            lines.append("Current trajectory:")
            traj_summary = self.summarize_trajectory(
                working.react_trajectory[-3:]
            )
            if traj_summary:
                lines.append(f"  {traj_summary}")

        return "\n".join(lines)
