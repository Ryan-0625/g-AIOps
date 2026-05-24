"""LangGraph state graph topology for the Brain execution loop — v2.0 Triple Loop.

Flow:
  Analyst → Memory Load → [Plan (outer loop)
                              ↓
                           ReAct (middle loop: Thought→Action→Observation)
                              ↓
                           Reflect (inner loop: evaluate → continue/replan/backtrack)
                           ] × N → done

Memory Integration:
  - Episodic: past execution patterns (action + error_code similarity)
  - Semantic: knowledge base (known fixes, best practices)
  - Working: current session context (trajectory buffer, variables)

Auto-Deploy Integration:
  - When NO_AVAILABLE_WORKER → try Deployer templates first
  - If no template → CodeGenerator generates code → Deployer deploys → retry
"""

import asyncio
import json
import random
import time
from typing import Any, Optional

from core.state import GraphState
from agents.analyst import analyst_node
from agents.planner import planner_node
from agents.reflector import reflector_node
from agents.reactor import ReActEngine
from agents.deployer import Deployer
from agents.code_generator import CodeGenerator, CodeGenerationError
from llm.adapter import LLMAdapter
from llm.schemas import ALL_TOOLS, _llm_name, _action_name
from llm.context_window import compress_messages
from tools.master_client import MasterClient
from memory.episodic import EpisodicMemory, Episode
from memory.semantic import SemanticMemory, KnowledgeEntry
from memory.working import WorkingMemory
from memory.summarizer import MemorySummarizer
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
        name_display = _action_name(fn['name'])
        lines.append(f"  - {name_display}({param_str}): {fn['description']}")
    return "\n".join(lines)


class GraphEngine:
    """LangGraph execution engine — v2.0 Triple Loop.

    Flow hierarchy:
      Outer (Plan): Define/refine plan, track overall progress
      Middle (ReAct): Thought→Action→Observation loop per step
      Inner (Reflect): Evaluate results, memory storage, cycle detection

    Each trace_id runs as an independent asyncio task.
    Sessions are isolated — no shared mutable state.
    """

    def __init__(self, llm: LLMAdapter, master: MasterClient, read_only: bool = False,
                 llm_max_retries: int = 2, metrics: Any = None):
        self.llm = llm
        self.master = master
        self.read_only = read_only
        self.llm_max_retries = llm_max_retries
        self.metrics = metrics
        self.degraded = False
        self.deployer = Deployer(master)
        self.code_generator = CodeGenerator(llm)
        self.react_engine = ReActEngine(llm)

        # Memory systems
        self.episodic_memory = EpisodicMemory()
        self.semantic_memory = SemanticMemory()
        self.memory_summarizer = MemorySummarizer()

        self.active_sessions: dict[str, asyncio.Task] = {}
        self.completed_sessions: dict[str, dict] = {}
        self._tool_descriptions = _build_tool_descriptions()

    @property
    def is_degraded(self) -> bool:
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
        """Independent graph execution loop — v2.0 Triple Loop."""
        set_trace_id(state.trace_id)
        try:
            # ═══ Phase 0: Analyst — understand the context ═══
            state = await analyst_node(state, context, self.llm)

            # ═══ Phase 1: Memory Load — load relevant memories ═══
            state = await self._load_memories(state, context)

            # ═══ Phase 2: Main Triple Loop ═══
            while True:
                # ── Outer Loop: Plan ──
                llm_response = await self._call_llm(state, context)
                if llm_response is None:
                    if self.read_only:
                        self.degraded = True
                        state.conclusion = "LLM unavailable — read-only mode."
                        break
                    state.needs_human = True
                    state.conclusion = "LLM unavailable after retries. Escalating to human."
                    break

                state = await planner_node(state, llm_response)
                if not state.plan:
                    if not state.needs_human:
                        state.needs_human = True
                        state.conclusion = "Planner could not create a valid plan."
                    break

                # Execute each plan step through ReAct + Reflect
                while state.current_step < len(state.plan) and not state.needs_human:
                    step = state.plan[state.current_step]
                    state.last_action = step["action"]

                    # ── Middle Loop: ReAct (Thought→Action→Observation) ──
                    react_result = await self.react_engine.execute_react_loop(
                        state=state,
                        step=step,
                        context=context,
                        tool_descriptions=self._tool_descriptions,
                    )

                    # Store trajectory
                    if react_result.get("trajectory"):
                        for traj_step in react_result["trajectory"]:
                            # Store to working memory via state
                            state.react_trajectory.append(traj_step)

                    # ── Handle deploy signal from ReAct ──
                    if react_result.get("status") == "needs_deploy":
                        deploy_success = await self._auto_deploy_tool(state, step)
                        if deploy_success:
                            # Retry execution after deployment
                            state.add_summary(f"Deployed missing tool: {step['action']}")
                            continue  # Go back to ReAct
                        else:
                            state.last_status = "failure"
                            state.last_error = "TOOL_DEPLOY_FAILED"
                    else:
                        state.last_status = react_result.get("status", "failure")
                        state.last_data = react_result.get("data", {})

                    # Handle truncation notice
                    if state.last_data and state.last_data.get("_truncated"):
                        state.truncated_responses.append(True)

                    # ── Inner Loop: Reflect ──
                    state = await reflector_node(state)

                    # Store to episodic memory
                    await self._store_episodic(state, step, context)

                    if state.needs_human or state.cycle_detected:
                        break

                if state.needs_human or state.cycle_detected:
                    break

                # Replan or done
                if not state.plan:
                    state.current_step = 0
                    continue

                if state.is_done():
                    self._finalize_conclusion(state)
                    break

            # Ensure conclusion always exists
            self._ensure_conclusion(state)

            logger.info("Session ended", extra={
                "data": {
                    "trace_id": state.trace_id,
                    "status": "needs_human" if state.needs_human else "completed",
                    "conclusion": state.conclusion,
                    "steps": len(state.summaries),
                    "react_trajectory": len(state.react_trajectory),
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
            self.completed_sessions[state.trace_id] = state.to_dict()
            self.active_sessions.pop(state.trace_id, None)

    # ── Memory Integration ────────────────────────────────────────────────

    async def _load_memories(self, state: GraphState, context: str) -> GraphState:
        """Load relevant episodic and semantic memories into state."""
        try:
            # Episodic: find similar past executions
            similar = await self.episodic_memory.retrieve_similar(
                action=state.last_action or "",
                error_code=state.last_error or None,
                top_k=3,
            )
            state.relevant_episodes = similar

            # Semantic: find knowledge for current context
            knowledge = await self.semantic_memory.query(
                action=state.last_action or "",
                error_code=state.last_error or None,
                context=context,
            )
            state.semantic_knowledge = knowledge

            # Build memory context string
            memory_ctx = self.memory_summarizer.build_memory_prompt(
                episodic=similar,
                semantic=knowledge,
                working=None,  # Will be populated during ReAct
            )
            state.memory_context = memory_ctx

        except Exception as e:
            logger.warning(f"Memory load failed (non-critical): {e}")
            state.memory_context = ""

        return state

    async def _store_episodic(self, state: GraphState, step: dict, context: str) -> None:
        """Store execution result to episodic memory."""
        try:
            episode = Episode(
                trace_id=state.trace_id,
                context_hash=hash(context[:500]) & 0xFFFFFFFF,
                action=step.get("action", "unknown"),
                params=step.get("params", {}),
                status=state.last_status or "failure",
                error_code=state.last_error or None,
                error_message=state.last_error or None,
                summary=state.summaries[-1] if state.summaries else "",
                duration_ms=0,
                timestamp=int(time.time()),
                react_steps=len(state.react_trajectory),
            )
            await self.episodic_memory.store(episode)
        except Exception as e:
            logger.warning(f"Episodic store failed: {e}")

    # ── Auto-Deploy Integration ───────────────────────────────────────────

    async def _auto_deploy_tool(self, state: GraphState, step: dict) -> bool:
        """Try to deploy a missing tool — via template or code generation."""
        action_name = step.get("action", "")

        # Strategy 1: Deployer templates
        if self.deployer.has_template(action_name):
            logger.info("Deploying from template", extra={
                "data": {"action": action_name, "trace_id": state.trace_id},
            })
            deployed = await self.deployer.deploy(
                action=action_name,
                trace_id=state.trace_id,
            )
            if deployed:
                await asyncio.sleep(2)
                return True

        # Strategy 2: LLM Code Generation (v2.0)
        if self.llm and not self.degraded:
            task_description = f"Create a tool that performs: {action_name.replace('.', ' ')}"
            if step.get("params"):
                task_description += f" with parameters: {json.dumps(step['params'])[:200]}"

            logger.info("Generating tool code via LLM", extra={
                "data": {"action": action_name, "trace_id": state.trace_id},
            })

            try:
                generated = await self.code_generator.generate(
                    task=task_description,
                    language="bash",
                    timeout=30,
                )
                logger.info(f"Code generated for {action_name}", extra={
                    "data": {"risk_level": generated.risk_level, "trace_id": state.trace_id},
                })

                # Deploy via Master's tool-deploy API
                deploy_result = await self.master.execute(
                    action="tool.create",
                    params={
                        "name": generated.action,
                        "script": generated.code,
                        "interpreter": generated.language,
                        "description": generated.description,
                        "risk_level": generated.risk_level,
                        "timeout": generated.timeout,
                    },
                    trace_id=state.trace_id,
                )

                if deploy_result.get("status") == "success":
                    await asyncio.sleep(2)
                    state.add_summary(f"Auto-deployed tool: {generated.action}")
                    state.deployed_tools.add(generated.action)
                    return True
                else:
                    logger.warning("Deploy failed after code gen", extra={
                        "data": {"action": action_name, "error": deploy_result},
                    })
            except CodeGenerationError as e:
                logger.warning(f"Code generation failed for {action_name}: {e}")
            except Exception as e:
                logger.warning(f"Auto-deploy failed for {action_name}: {e}")

        return False

    # ── LLM Call with Memory Enhancement ─────────────────────────────────

    async def _call_llm(self, state: GraphState, context: str) -> str | None:
        """Call the LLM with memory-enhanced context."""
        if self.degraded:
            return None

        system_content = SYSTEM_PROMPT.format(tool_descriptions=self._tool_descriptions)

        # Append memory context if available
        if state.memory_context:
            system_content += f"\n\n{state.memory_context}"

        # Append ReAct trajectory if available
        if state.react_trajectory:
            traj_summary = self.memory_summarizer.summarize_trajectory(
                state.react_trajectory[-3:]
            )
            if traj_summary:
                system_content += f"\n\nRecent trajectory: {traj_summary}"

        # Append available Worker context
        try:
            workers = await self.master.list_workers()
            if workers:
                worker_lines = ["\nAvailable workers:"]
                for w in workers:
                    actions = ", ".join(w.get("actions", [])[:8])
                    wl = w.get("current_load", 0)
                    mc = w.get("max_concurrent", 1)
                    worker_lines.append(f"  - {w['worker_id']}: [{wl}/{mc} load] {actions}")
                worker_lines.append(
                    'Use "target_worker_id" to direct a tool to a specific worker.'
                )
                system_content += "\n" + "\n".join(worker_lines)
        except Exception:
            pass

        # Build prompt
        if state.summaries:
            history = "\n".join(state.summaries[-5:])
            if state.last_error:
                prompt = (
                    f"Original request: {context}\n\n"
                    f"Previous steps:\n{history}\n\n"
                    f"The last action [{state.last_action}] failed with error: {state.last_error}\n"
                    "Determine the next action."
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
                "Analyze this request and respond with a JSON tool call."
            )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]
        messages = compress_messages(messages, state.summaries)

        # Retry loop
        last_error: str | None = None
        for attempt in range(self.llm_max_retries + 1):
            if self.metrics:
                self.metrics.llm_calls_total += 1
            try:
                t0 = time.monotonic()
                response = await self.llm.chat(messages=messages, tools=ALL_TOOLS, timeout=30.0)
                elapsed = time.monotonic() - t0
                if self.read_only and elapsed > 20.0:
                    self.degraded = True
                    return None
                if isinstance(response, dict):
                    message = response.get("message", {})
                    tool_calls = message.get("tool_calls", [])
                    if tool_calls:
                        fn = tool_calls[0].get("function", {})
                        raw_params = fn.get("arguments", {})
                        if isinstance(raw_params, str):
                            try:
                                raw_params = json.loads(raw_params)
                            except json.JSONDecodeError:
                                raw_params = {}
                        return json.dumps({
                            "action": _action_name(fn.get("name", "")),
                            "params": raw_params,
                        })
                    content = message.get("content", "")
                    if content.strip():
                        return content
                return str(response) if response else None
            except (asyncio.TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                last_error = str(e)
                if attempt < self.llm_max_retries:
                    delay = min(1.0 * (2 ** attempt), 15.0)
                    await asyncio.sleep(delay * random.uniform(0.75, 1.25))
            except Exception as e:
                last_error = str(e)
                if self.metrics:
                    self.metrics.llm_errors_total += 1
                return None

        if self.metrics:
            self.metrics.llm_errors_total += 1
        return None

    # ── Helpers ───────────────────────────────────────────────────────────

    def _finalize_conclusion(self, state: GraphState) -> None:
        """Generate conclusion when plan completes."""
        if state.conclusion:
            return
        has_failures = any("FAIL:" in s for s in state.summaries)
        if has_failures and state.last_action:
            state.conclusion = (
                f"Operation failed: {state.last_action} could not be "
                f"executed on any available worker."
            )
        else:
            state.conclusion = "Plan executed."
        state.add_summary(state.conclusion)

    def _ensure_conclusion(self, state: GraphState) -> None:
        """Ensure a meaningful conclusion always exists."""
        if state.conclusion:
            return
        if state.needs_human:
            state.conclusion = "Session ended — needs human intervention."
        elif state.cycle_detected:
            state.conclusion = "Session ended — cycle detected."
        else:
            state.conclusion = "Session ended."

    # ── Session Management ────────────────────────────────────────────────

    async def get_session_status(self, trace_id: str) -> dict[str, Any]:
        if trace_id in self.completed_sessions:
            result = self.completed_sessions[trace_id]
            return {"trace_id": trace_id, "status": "completed", **result}
        task = self.active_sessions.get(trace_id)
        if task is None:
            return {"trace_id": trace_id, "status": "not_found"}
        if task.done():
            exc = task.exception()
            if exc:
                return {"trace_id": trace_id, "status": "failed", "error": str(exc)}
            return {"trace_id": trace_id, "status": "completed"}
        return {"trace_id": trace_id, "status": "running"}

    def pop_session_result(self, trace_id: str) -> dict | None:
        return self.completed_sessions.pop(trace_id, None)
