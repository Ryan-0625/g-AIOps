"""ReAct Engine — Thought→Action→Observation 推理循环。

ReAct 是中层循环的核心，负责：
1. Thought: 根据当前状态 + 记忆 + 轨迹生成下一步推理
2. Action: 决定调用哪个工具（或部署新工具）
3. Observation: 解析工具输出，提取关键信息
4. 循环直到任务完成或达到最大步数

融合 Plan-and-Execute 的规划能力 + ReAct 的灵活性 + Reflection 的自省能力。
"""

import json
from typing import Any, Optional

from core.state import GraphState
from llm.sanitizer import LLMOutputSanitizer
from llm.adapter import LLMAdapter
from tools.tool_registry import REGISTRY
from logger.structured_logger import get_logger

logger = get_logger()
sanitizer = LLMOutputSanitizer(REGISTRY)

MAX_REACT_STEPS = 5  # 单步 ReAct 最大循环次数

REACT_SYSTEM_PROMPT = """You are gAIOps Brain's reasoning engine. Follow the ReAct pattern:

1. **Thought**: Analyze the current situation. What do you know? What do you need?
2. **Action**: Choose ONE tool from the list below. Output JSON: {{"action": "...", "params": {{...}}}}
3. **Observation**: You will receive the tool output. Use it for the next Thought.

Available tools:
{tool_descriptions}

Rules:
- Use tools one at a time
- If a tool fails, analyze the error and try a different approach
- If the action requires a tool that doesn't exist, output: {{"action": "__deploy__", "params": {{"task": "...", "language": "bash"}}}}
- When the task is complete, output: {{"action": "__done__", "params": {{"result": "..."}}}}

Think step by step. Be concise but precise."""


class ReActEngine:
    """ReAct 推理引擎。"""

    def __init__(self, llm: LLMAdapter):
        self.llm = llm

    async def execute_react_loop(
        self,
        state: GraphState,
        step: dict,
        context: str,
        tool_descriptions: str,
    ) -> dict:
        """执行 ReAct 中层循环。"""
        trajectory = []

        for react_step in range(MAX_REACT_STEPS):
            # ── Thought ──
            thought = await self._generate_thought(
                state, step, trajectory, context, tool_descriptions
            )
            if thought is None:
                return {
                    "status": "failure",
                    "error": {"code": "REACT_THOUGHT_FAILED", "message": "Failed to generate thought"},
                    "trajectory": trajectory,
                    "react_steps": react_step,
                }

            # ── Action ──
            action_result = await self._execute_action(state, thought, step)
            trajectory.append({
                "thought": thought.get("content", ""),
                "action": action_result.get("action", step["action"]),
                "observation": action_result,
            })

            # ── Check for __done__ signal ──
            if action_result.get("action") == "__done__":
                return {
                    "status": "success",
                    "data": action_result.get("data", {}),
                    "conclusion": action_result.get("params", {}).get("result", ""),
                    "trajectory": trajectory,
                    "react_steps": react_step + 1,
                }

            # ── Success → return ──
            if action_result.get("status") == "success":
                return {
                    "status": "success",
                    "data": action_result.get("data", {}),
                    "trajectory": trajectory,
                    "react_steps": react_step + 1,
                }

            # ── Failure: check if error is actionable ──
            error = action_result.get("error", {})
            error_code = error.get("code", "")

            if error_code == "NO_AVAILABLE_WORKER":
                # Tool not available — signal deployer
                return {
                    "status": "needs_deploy",
                    "action": step["action"],
                    "error": error,
                    "trajectory": trajectory,
                    "react_steps": react_step + 1,
                }

            # Continue ReAct loop with observation
            continue

        # Max ReAct steps reached without completion
        return {
            "status": "failure",
            "error": {"code": "REACT_MAX_STEPS", "message": f"ReAct loop exceeded {MAX_REACT_STEPS} steps"},
            "trajectory": trajectory,
            "react_steps": MAX_REACT_STEPS,
        }

    async def _generate_thought(
        self,
        state: GraphState,
        step: dict,
        trajectory: list,
        context: str,
        tool_descriptions: str,
    ) -> Optional[dict]:
        """生成推理步骤。"""
        # Build context with trajectory
        traj_text = self._format_trajectory(trajectory)
        history_text = "\n".join(state.summaries[-3:]) if state.summaries else ""

        system_prompt = REACT_SYSTEM_PROMPT.format(
            tool_descriptions=tool_descriptions
        )

        user_prompt = (
            f"Original request: {context}\n\n"
            f"Current step: Execute '{step['action']}' with params: {json.dumps(step.get('params', {}))}\n\n"
        )
        if traj_text:
            user_prompt += f"Previous attempts:\n{traj_text}\n\n"
        if history_text:
            user_prompt += f"Session history:\n{history_text}\n\n"
        user_prompt += "What is your next action? Respond with JSON."

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=15.0,
            )
            if isinstance(response, dict):
                content = response.get("message", {}).get("content", "")
                if content:
                    return {"content": content, "raw": response}
            return None
        except Exception as e:
            logger.warning(f"ReAct thought generation failed: {e}")
            return None

    async def _execute_action(
        self, state: GraphState, thought: dict, step: dict
    ) -> dict:
        """执行 Action（工具调用）。"""
        content = thought.get("content", "")

        # Parse JSON from LLM response
        try:
            # Try to extract JSON from the content
            decision = self._extract_json(content)
        except Exception:
            decision = None

        if not decision:
            return {
                "status": "failure",
                "error": {"code": "INVALID_LLM_OUTPUT", "message": "Could not parse LLM response as JSON"},
                "action": step["action"],
            }

        action = decision.get("action", step["action"])

        # Handle special actions
        if action == "__done__":
            return {
                "status": "success",
                "action": "__done__",
                "data": {},
                "params": decision.get("params", {}),
            }

        if action == "__deploy__":
            return {
                "status": "failure",
                "action": "__deploy__",
                "error": {"code": "NO_AVAILABLE_WORKER", "message": f"Need to deploy: {decision.get('params', {}).get('task', 'unknown')}"},
            }

        # Regular tool call
        params = decision.get("params", {})
        return {
            "status": "pending",
            "action": action,
            "params": params,
        }

    def _extract_json(self, text: str) -> Optional[dict]:
        """从文本中提取 JSON。"""
        import re
        # Try to find ```json ... ``` block
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find { ... } directly
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _format_trajectory(self, trajectory: list) -> str:
        """将轨迹格式化为提示文本。"""
        if not trajectory:
            return ""
        lines = []
        for i, t in enumerate(trajectory, 1):
            thought = t.get("thought", "")[:150]
            action = t.get("action", "?")
            obs = t.get("observation", {})
            status = obs.get("status", "?")
            lines.append(f"  [{i}] Thought: {thought}")
            lines.append(f"      Action: {action} → {status}")
        return "\n".join(lines)
