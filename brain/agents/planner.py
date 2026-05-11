"""Planner node — creates an execution plan using LLM."""

from core.state import GraphState
from llm.sanitizer import LLMOutputSanitizer
from logger.structured_logger import get_logger
from tools.tool_registry import REGISTRY

logger = get_logger()
sanitizer = LLMOutputSanitizer(REGISTRY)


async def planner_node(state: GraphState, llm_response: str | None = None) -> GraphState:
    """Generate a plan of tool calls.

    In the full implementation, this calls the LLM with the current context.
    For bootstrap, llm_response can be passed directly.
    """
    if not state.plan and llm_response:
        sanitized = sanitizer.sanitize_tool_call(llm_response)
        if sanitized.error:
            logger.warning("Planner output rejected", extra={"error_code": sanitized.error})
            state.last_error = sanitized.error
            return state

        if sanitized.action:
            state.plan = [
                {"action": sanitized.action, "params": sanitized.params}
            ]
            state.add_summary(f"Plan: {sanitized.action}")

    logger.info("Planner ready", extra={"data": {"steps": len(state.plan), "trace_id": state.trace_id}})
    return state
