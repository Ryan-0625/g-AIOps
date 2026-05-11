"""LangGraph state graph topology for the Brain execution loop.

Flow:
  Analyst → Planner → [Execute → Reflector]×N → done
                         ↑         │
                         └─ replan ─┘
"""

import asyncio
import json
from typing import Any

from core.state import GraphState
from agents.analyst import analyst_node
from agents.planner import planner_node
from agents.reflector import reflector_node
from llm.adapter import LLMAdapter
from llm.schemas import ALL_TOOLS
from llm.context_window import compress_messages
from tools.master_client import MasterClient
from logger.structured_logger import get_logger
from logger.trace_context import generate_trace_id, set_trace_id

logger = get_logger()

SYSTEM_PROMPT = """You are gAIOps Brain, an intelligent AI operations decision engine.

Available tools:
{tool_descriptions}

Respond with a JSON tool call in the format:
{{"action": "tool_name", "params": {{"key": "value"}}}}

Rules:
- Only use tools from the list above.
- Always provide required parameters.
- If a tool fails, analyze the error and either retry with adjusted params or propose a different approach."""


def _build_tool_descriptions() -> str:
    lines = []
    for t in ALL_TOOLS:
        fn = t["function"]
        params = fn.get("parameters", {}).get("properties", {})
        param_str = ", ".join(
            f"{k}: {v.get('type', 'any')}{'(required)' if k in fn.get('parameters', {}).get('required', []) else ''}"
            for k, v in params.items()
        )
        lines.append(f"  - {fn['name']}({param_str}): {fn['description']}")
    return "\n".join(lines)


class GraphEngine:
    """LangGraph execution engine.

    Each trace_id runs as an independent asyncio task.
    Sessions are isolated — no shared mutable state.

    Supports degraded read-only mode: when the LLM is unavailable or slow,
    the engine skips inference and returns existing results rather than
    escalating to human intervention.
    """

    def __init__(self, llm: LLMAdapter, master: MasterClient, read_only: bool = False):
        self.llm = llm
        self.master = master
        self.read_only = read_only
        self.degraded = False
        self.active_sessions: dict[str, asyncio.Task] = {}
        self._tool_descriptions = _build_tool_descriptions()

    @property
    def is_degraded(self) -> bool:
        """True when engine is operating in degraded read-only mode."""
        return self.degraded

    async def start_session(self, context: str) -> str:
        """Start a new reasoning session. Returns trace_id."""
        trace_id = generate_trace_id()
        state = GraphState(trace_id=trace_id)
        task = asyncio.create_task(self._run_graph(state, context))
        self.active_sessions[trace_id] = task
        logger.info("Session started", extra={"data": {"trace_id": trace_id, "context": context[:100]}})
        return trace_id

    async def _run_graph(self, state: GraphState, context: str) -> None:
        """Independent graph execution loop for one session."""
        set_trace_id(state.trace_id)
        try:
            # Phase 1: Analyst — understand the context.
            state = await analyst_node(state, context, self.llm)

            # Main execution loop.
            while True:
                # Call LLM → Planner.
                llm_response = await self._call_llm(state, context)
                if llm_response is None:
                    if self.read_only:
                        self.degraded = True
                        state.conclusion = "LLM unavailable — read-only mode. Returning current results."
                        logger.warning("Degraded to read-only mode", extra={"data": {"trace_id": state.trace_id}})
                        break
                    state.needs_human = True
                    state.conclusion = "LLM unavailable after retries. Escalating to human."
                    break

                state = await planner_node(state, llm_response)
                if not state.plan:
                    if not state.needs_human:
                        state.needs_human = True
                        state.conclusion = "Planner could not create a valid plan. Escalating to human."
                    break

                # Phase 3 & 4: Execute each step → Reflector evaluates.
                while state.current_step < len(state.plan) and not state.needs_human:
                    step = state.plan[state.current_step]
                    state.last_action = step["action"]

                    result = await self.master.execute(
                        action=step["action"],
                        params=step.get("params", {}),
                        trace_id=state.trace_id,
                    )

                    state.last_status = result.get("status", "failure")
                    state.last_data = result.get("data", {})

                    error = result.get("error", {})
                    state.last_error = error.get("code", "") if error else ""

                    if result.get("truncated"):
                        state.truncated_responses.append(True)
                        state.last_data["_truncation_notice"] = (
                            f"[Response truncated, original size: {result.get('truncated_at', 0)} bytes]"
                        )

                    state = await reflector_node(state)

                    if state.needs_human or state.cycle_detected:
                        break

                if state.needs_human or state.cycle_detected:
                    break

                # Replan: reflector cleared the plan → go back to Planner.
                if not state.plan:
                    state.current_step = 0
                    continue

                # Plan completed.
                if state.is_done():
                    if not state.conclusion:
                        state.conclusion = "Plan executed."
                        state.add_summary(state.conclusion)
                    break

            # Ensure a conclusion always exists.
            if not state.conclusion:
                if state.needs_human:
                    state.conclusion = "Session ended — needs human intervention."
                elif state.cycle_detected:
                    state.conclusion = "Session ended — cycle detected."
                else:
                    state.conclusion = "Session ended."

            logger.info("Session ended", extra={
                "data": {
                    "trace_id": state.trace_id,
                    "status": "needs_human" if state.needs_human else "completed",
                    "conclusion": state.conclusion,
                    "steps": len(state.summaries),
                }
            })

        except Exception as e:
            logger.error("Session failed", extra={
                "error_code": "BRAIN_SESSION_FAILED",
                "data": {"trace_id": state.trace_id, "error": str(e)},
            })
            state.needs_human = True
            state.conclusion = f"Brain session failed: {e}"
        finally:
            self.active_sessions.pop(state.trace_id, None)

    async def _call_llm(self, state: GraphState, context: str) -> str | None:
        """Call the LLM for planning. Returns raw response string or None on failure."""
        # If already degraded, skip LLM call entirely.
        if self.degraded:
            logger.info("Skipping LLM call — engine in degraded mode", extra={"data": {"trace_id": state.trace_id}})
            return None

        system_content = SYSTEM_PROMPT.format(tool_descriptions=self._tool_descriptions)

        if state.summaries:
            history = "\n".join(state.summaries[-5:])
            if state.last_error:
                prompt = (
                    f"Original request: {context}\n\n"
                    f"Previous steps:\n{history}\n\n"
                    f"The last action [{state.last_action}] failed with error: {state.last_error}\n"
                    "Determine the next action. Create a revised tool call."
                )
            else:
                prompt = (
                    f"Original request: {context}\n\n"
                    f"Previous steps:\n{history}\n\n"
                    "Determine the next action."
                )
        else:
            prompt = (
                f"Original request: {context}\n\n"
                "Analyze this request and respond with a JSON tool call "
                "in the format: {\"action\": \"tool_name\", \"params\": {...}}"
            )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        # Compress if needed.
        messages = compress_messages(messages, state.summaries)

        import time
        try:
            t0 = time.monotonic()
            response = await self.llm.chat(messages=messages, tools=ALL_TOOLS, timeout=30.0)
            elapsed = time.monotonic() - t0
            # Auto-degrade if LLM response is consistently slow (>20s).
            if self.read_only and elapsed > 20.0:
                self.degraded = True
                logger.warning("LLM response slow — degrading to read-only mode", extra={
                    "data": {"trace_id": state.trace_id, "elapsed_seconds": round(elapsed, 1)},
                })
            if isinstance(response, dict):
                message = response.get("message", {})
                # Ollama tool_calls format.
                tool_calls = message.get("tool_calls", [])
                if tool_calls:
                    fn = tool_calls[0].get("function", {})
                    raw_params = fn.get("arguments", {})
                    # Tool call arguments are JSON strings per API spec.
                    if isinstance(raw_params, str):
                        try:
                            raw_params = json.loads(raw_params)
                        except json.JSONDecodeError:
                            raw_params = {}
                    return json.dumps({
                        "action": fn.get("name", ""),
                        "params": raw_params,
                    })
                # Plain text response.
                content = message.get("content", "")
                if content.strip():
                    return content
            return str(response) if response else None
        except Exception as e:
            logger.error("LLM call failed", extra={
                "error_code": "BRAIN_LLM_UNAVAILABLE",
                "data": {"trace_id": state.trace_id, "error": str(e)},
            })
            return None

    async def get_session_status(self, trace_id: str) -> dict[str, Any]:
        """Check if a session is still running or completed."""
        task = self.active_sessions.get(trace_id)
        if task is None:
            return {"trace_id": trace_id, "status": "not_found"}
        if task.done():
            exc = task.exception()
            if exc:
                return {"trace_id": trace_id, "status": "failed", "error": str(exc)}
            return {"trace_id": trace_id, "status": "completed"}
        return {"trace_id": trace_id, "status": "running"}
