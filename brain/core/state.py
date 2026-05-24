"""Graph state definition for LangGraph execution — v2.0 Triple Loop."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GraphState:
    """State passed between LangGraph nodes — v2.0 Triple Loop.

    Extensions for v2.0:
    - Memory integration (relevant_episodes, semantic_knowledge, memory_context)
    - ReAct trajectory (react_trajectory, react_step_count)
    - Code generation tracking (deployed_tools, deploy_attempts)
    """

    # Tracing.
    trace_id: str = ""

    # Plan execution.
    plan: list[dict[str, Any]] = field(default_factory=list)
    current_step: int = 0

    # Execution results.
    last_action: str = ""
    last_status: str = ""
    last_error: str = ""
    last_data: dict[str, Any] = field(default_factory=dict)

    # Summaries for context window compression.
    summaries: list[str] = field(default_factory=list)

    # Flow control.
    needs_human: bool = False
    cycle_detected: bool = False
    conclusion: str = ""

    # Truncation awareness.
    truncated_responses: list[bool] = field(default_factory=list)

    # ── v2.0: Memory Integration ──
    memory_context: str = ""
    relevant_episodes: list = field(default_factory=list)
    semantic_knowledge: Optional[Any] = None
    working_memory: Optional[Any] = None  # WorkingMemory instance (lazy init)

    # ── v2.0: ReAct Trajectory ──
    react_trajectory: list[dict] = field(default_factory=list)
    react_step_count: int = 0
    max_react_steps: int = 5

    # ── v2.0: Dynamic Tool Tracking ──
    deployed_tools: set[str] = field(default_factory=set)
    deploy_attempts: int = 0

    def advance(self) -> None:
        self.current_step += 1

    def is_done(self) -> bool:
        return self.current_step >= len(self.plan) or self.needs_human

    def add_summary(self, summary: str) -> None:
        self.summaries.append(summary)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (backward-compatible format)."""
        result = {
            "trace_id": self.trace_id,
            "conclusion": self.conclusion,
            "summaries": list(self.summaries),
            "needs_human": self.needs_human,
            "cycle_detected": self.cycle_detected,
            "last_action": self.last_action,
            "last_status": self.last_status,
            "last_data": self.last_data,
            "truncated": len(self.truncated_responses) > 0,
        }
        # v2.0 fields (optional — old consumers ignore)
        result["react_steps"] = self.react_step_count
        result["deployed_tools"] = list(self.deployed_tools)
        return result
