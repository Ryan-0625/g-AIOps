"""Tests for planner_node — plan generation from LLM responses."""

from core.state import GraphState
from agents.planner import planner_node


class TestPlannerNode:
    async def test_valid_tool_call_creates_plan(self):
        state = GraphState(trace_id="test-1")
        llm_response = '{"action": "ping.icmp", "params": {"target": "10.0.0.1"}}'
        result = await planner_node(state, llm_response)
        assert len(result.plan) == 1
        assert result.plan[0]["action"] == "ping.icmp"
        assert result.plan[0]["params"]["target"] == "10.0.0.1"
        assert not result.needs_human

    async def test_multi_step_plan_not_supported(self):
        """Current planner only handles single-step plans from one LLM call."""
        state = GraphState(trace_id="test-2")
        llm_response = (
            '[{"action": "ping.icmp", "params": {"target": "h1"}},'
            '{"action": "disk.usage", "params": {}}]'
        )
        result = await planner_node(state, llm_response)
        # The sanitizer only looks for a single action/params JSON.
        # An array will fail parsing validation.
        assert len(result.plan) == 0
        assert result.last_error is not None

    async def test_unknown_tool_rejected(self):
        state = GraphState(trace_id="test-3")
        llm_response = '{"action": "unknown.tool", "params": {}}'
        result = await planner_node(state, llm_response)
        assert len(result.plan) == 0
        assert result.last_error is not None
        assert "UNKNOWN_TOOL" in result.last_error

    async def test_missing_required_params(self):
        state = GraphState(trace_id="test-4")
        llm_response = '{"action": "ping.icmp", "params": {}}'
        result = await planner_node(state, llm_response)
        assert len(result.plan) == 0
        assert result.last_error is not None
        assert "MISSING_PARAMS" in result.last_error

    async def test_empty_response_no_plan(self):
        state = GraphState(trace_id="test-5")
        result = await planner_node(state, None)
        assert len(result.plan) == 0

    async def test_broken_json_no_plan(self):
        state = GraphState(trace_id="test-6")
        result = await planner_node(state, "{not json}")
        assert len(result.plan) == 0
        assert result.last_error is not None

    async def test_plan_does_not_overwrite_existing(self):
        state = GraphState(
            trace_id="test-7",
            plan=[{"action": "disk.usage", "params": {"path": "/"}}],
        )
        # With an existing plan, planner should not overwrite.
        llm_response = '{"action": "ping.icmp", "params": {"target": "10.0.0.1"}}'
        result = await planner_node(state, llm_response)
        assert len(result.plan) == 1
        assert result.plan[0]["action"] == "disk.usage"
