"""Tests for GraphEngine — execution loop, truncation, replan, cycle detection."""

import json
from typing import Any

from core.graph import GraphEngine
from core.state import GraphState
from llm.adapter import LLMAdapter


class FakeLLM(LLMAdapter):
    """Controlled fake LLM for deterministic graph testing."""

    def __init__(self):
        self.calls = []
        self.responses: list[dict[str, Any]] = []

    def add_response(self, action: str, params: dict | None = None):
        """Queue an LLM response that returns a tool_call."""
        self.responses.append({
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": action,
                            "arguments": json.dumps(params or {}),
                        }
                    }
                ]
            }
        })

    def add_empty_response(self):
        """Queue a None response (simulates LLM failure)."""
        self.responses.append(None)

    async def chat(self, messages, tools=None, timeout=30.0) -> dict[str, Any] | None:
        self.calls.append({"messages": messages, "tools": tools})
        if self.responses:
            return self.responses.pop(0)
        return None

    async def chat_stream(self, messages, tools=None):
        yield {"error": "not implemented"}
        return

    async def close(self):
        pass


class FakeMasterClient:
    """Controlled fake MasterClient for deterministic graph testing."""

    def __init__(self):
        self.executions = []
        self.responses: list[dict[str, Any]] = []

    def add_response(self, status="success", data=None, error=None, truncated=False):
        self.responses.append({
            "status": status,
            "data": data or {},
            "error": error,
            "truncated": truncated,
        })

    async def execute(self, action, params=None, trace_id="", priority=0, ttl_seconds=30):
        self.executions.append({"action": action, "params": params})
        if self.responses:
            return self.responses.pop(0)
        return {"status": "success", "data": {}, "truncated": False}


class TestGraphEngine:
    async def test_single_step_success(self):
        llm = FakeLLM()
        llm.add_response("analyst.done", {"intent": "ping"})  # analyst node
        llm.add_response("ping.icmp", {"target": "10.0.0.1"})  # planner

        master = FakeMasterClient()
        master.add_response(status="success", data={"latency_ms": 5})

        engine = GraphEngine(llm, master)
        state = GraphState(trace_id="graph-test-1")
        await engine._run_graph(state, "Ping 10.0.0.1")

        assert state.conclusion is not None
        assert len(state.summaries) > 0
        assert len(master.executions) == 1
        assert master.executions[0]["action"] == "ping.icmp"

    async def test_truncation_injection(self):
        """Truncated response should set the _truncation_notice flag."""
        llm = FakeLLM()
        llm.add_response("analyst.done", {"severity": "info"})  # analyst
        llm.add_response("disk.usage", {"path": "/"})  # planner

        master = FakeMasterClient()
        master.add_response(
            status="success",
            data={"disk": "lots-of-data...more-than-enough"},
            truncated=True,
            error=None,
        )

        engine = GraphEngine(llm, master)
        state = GraphState(trace_id="graph-test-trunc")
        await engine._run_graph(state, "Check disk usage")

        assert len(state.truncated_responses) == 1
        assert state.truncated_responses[0] is True
        assert "_truncation_notice" in state.last_data
        assert state.conclusion is not None

    async def test_replan_path(self):
        """When reflector clears the plan, the loop should replan."""
        llm = FakeLLM()
        llm.add_response("analyst.done", {})  # analyst
        llm.add_response("ping.icmp", {"target": "10.0.0.1"})  # planner call 1
        llm.add_response("ping.icmp", {"target": "10.0.0.2"})  # planner call 2 (replan)

        master = FakeMasterClient()
        # First execution fails (INVALID_PARAMS triggers replan in reflector).
        master.add_response(
            status="failure",
            data={},
            error={"code": "INVALID_PARAMS"},
        )
        # Second execution (after replan) succeeds.
        master.add_response(
            status="success",
            data={"latency_ms": 3},
        )

        engine = GraphEngine(llm, master)
        state = GraphState(trace_id="graph-test-replan")
        await engine._run_graph(state, "Ping 10.0.0.1")

        # Should have made 3 LLM calls (analyst + 2 planners) and 2 executions.
        assert len(llm.calls) == 3
        assert len(master.executions) == 2
        assert state.conclusion is not None

    async def test_llm_unavailable_escalates(self):
        """When LLM returns None, needs_human should be set."""
        llm = FakeLLM()
        llm.add_empty_response()

        master = FakeMasterClient()

        engine = GraphEngine(llm, master)
        state = GraphState(trace_id="graph-test-llm-down")
        await engine._run_graph(state, "Do something")

        assert state.needs_human is True
        assert "LLM unavailable" in state.conclusion

    async def test_session_lifecycle(self):
        """start_session and get_session_status should work end-to-end."""
        llm = FakeLLM()
        llm.add_response("analyst.done", {})  # analyst
        llm.add_response("ping.icmp", {"target": "127.0.0.1"})  # planner

        master = FakeMasterClient()
        master.add_response(status="success", data={"latency_ms": 1})

        engine = GraphEngine(llm, master)
        trace_id = await engine.start_session("Ping localhost")

        # Status should be "running" while the task is in progress.
        status_running = await engine.get_session_status(trace_id)
        assert status_running["status"] in ("running", "completed")

        # Wait for the session to finish.
        task = engine.active_sessions.get(trace_id)
        if task:
            await task

        # Session is popped from active_sessions on completion,
        # so get_session_status returns not_found.
        status_done = await engine.get_session_status(trace_id)
        assert status_done["status"] == "not_found"

        # But we can verify the task completed without exception.
        assert task is None or task.exception() is None

    async def test_nonexistent_session(self):
        engine = GraphEngine(FakeLLM(), FakeMasterClient())
        status = await engine.get_session_status("non-existent")
        assert status["status"] == "not_found"
