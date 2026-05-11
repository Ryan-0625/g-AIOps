"""Analyst node — understands the context and defines the problem."""

from typing import Any

from core.state import GraphState
from llm.adapter import LLMAdapter
from llm.schemas import ALL_TOOLS
from logger.structured_logger import get_logger

logger = get_logger()

ANALYST_PROMPT = """You are gAIOps Brain's Analyst. Your role is to analyze the incoming
request and determine:

1. **Intent** — what the user wants to achieve (e.g. check disk, restart service, troubleshoot)
2. **Severity** — how critical this is (low / medium / high / critical)
3. **Target** — what system or resource the request targets
4. **Suggested approach** — which tools from the list below are likely needed

Available tools:
{tool_descriptions}

Respond in JSON format:
{{"intent": "...", "severity": "...", "target": "...", "approach": "..."}}
"""


async def analyst_node(state: GraphState, context: str, llm: LLMAdapter | None = None) -> GraphState:
    """Analyse the incoming context using LLM, extracting intent and severity.

    Falls back to a simple text-based extraction when LLM is unavailable.
    """
    logger.info("Analyst analysing context", extra={"data": {"trace_id": state.trace_id}})

    if llm is not None and context.strip():
        try:
            tool_list = "\n".join(
                f"  - {t['function']['name']}: {t['function']['description']}"
                for t in ALL_TOOLS
            )
            system_prompt = ANALYST_PROMPT.format(tool_descriptions=tool_list)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ]

            response = await llm.chat(messages=messages, timeout=15.0)
            if isinstance(response, dict):
                content = response.get("message", {}).get("content", "")
                if content.strip():
                    state.add_summary(f"Analysis: {content[:300]}")
                    return state
        except Exception as e:
            logger.warning("Analyst LLM call failed, using fallback", extra={
                "data": {"trace_id": state.trace_id, "error": str(e)},
            })

    # Fallback: simple text-based analysis.
    ctx_lower = context.lower() if context else ""
    intent = "unknown"
    if any(kw in ctx_lower for kw in ["disk", "storage", "space", "usage", "mount"]):
        intent = "check disk usage"
    elif any(kw in ctx_lower for kw in ["ping", "reachable", "connectivity", "network", "latency"]):
        intent = "check network connectivity"
    elif any(kw in ctx_lower for kw in ["service", "restart", "stop", "start", "status", "nginx", "sshd"]):
        intent = "manage service"
    elif any(kw in ctx_lower for kw in ["log", "tail", "trace", "follow"]):
        intent = "inspect logs"
    elif any(kw in ctx_lower for kw in ["process", "kill", "ps", "running"]):
        intent = "manage process"

    prefix = context[:200] if context else "empty"
    state.add_summary(f"Analysed: intent={intent}, context={prefix}")

    return state
