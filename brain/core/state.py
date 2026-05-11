"""Graph state definition for LangGraph execution."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphState:
    """State passed between LangGraph nodes.

    Uses a compressed form to avoid token explosion — execution history is
    stored as text summaries rather than full records.
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

    def advance(self) -> None:
        self.current_step += 1

    def is_done(self) -> bool:
        return self.current_step >= len(self.plan) or self.needs_human

    def add_summary(self, summary: str) -> None:
        self.summaries.append(summary)
