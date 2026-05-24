"""Working Memory — 当前会话的短期上下文。

管理:
- 当前计划（plan stack）
- ReAct 轨迹缓冲（thought-action-observation 三元组）
- 当前目标与已完成子目标
- 临时变量（工具输出中提取的关键值）
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WorkingMemory:
    """当前会话的工作记忆。"""
    trace_id: str
    goal: str = ""                                  # 当前最高目标
    plan_stack: list[dict] = field(default_factory=list)  # 计划栈
    react_trajectory: list[dict] = field(default_factory=list)  # ReAct 轨迹
    variables: dict[str, Any] = field(default_factory=dict)  # 临时变量
    completed_goals: list[str] = field(default_factory=list)
    max_trajectory: int = 10                        # 最大轨迹保留数

    def add_react_step(
        self, thought: str, action: str, observation: dict
    ) -> None:
        """记录一个 ReAct 步骤。"""
        self.react_trajectory.append({
            "thought": thought,
            "action": action,
            "observation": observation,
            "timestamp": self._now(),
        })
        # 压缩: 保留最近的 max_trajectory 条
        if len(self.react_trajectory) > self.max_trajectory:
            self.react_trajectory = self.react_trajectory[-self.max_trajectory:]

    def set_variable(self, key: str, value: Any) -> None:
        """设置临时变量。"""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """获取临时变量。"""
        return self.variables.get(key, default)

    def get_recent_trajectory(self, n: int = 3) -> list[dict]:
        """获取最近的 N 条 ReAct 轨迹。"""
        return self.react_trajectory[-n:]

    def format_trajectory_for_prompt(self, n: int = 3) -> str:
        """将 ReAct 轨迹格式化为 LLM 友好的文本。"""
        recent = self.get_recent_trajectory(n)
        if not recent:
            return ""

        lines = ["[Recent Execution Trajectory]"]
        for i, step in enumerate(recent, 1):
            thought = step.get("thought", "")[:200]
            action = step.get("action", "?")
            obs = step.get("observation", {})
            status = obs.get("status", "?")
            error = obs.get("error", {})
            error_str = f" [{error.get('code', '')}]" if error else ""

            lines.append(f"  Step {i}: {thought}")
            lines.append(f"    Action: {action}{error_str}")
            lines.append(f"    Status: {status}")

        return "\n".join(lines)

    def _now(self) -> int:
        import time
        return int(time.time())
