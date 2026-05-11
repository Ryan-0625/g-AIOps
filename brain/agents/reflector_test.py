"""Tests for reflector_node — execution evaluation and cycle detection."""

from core.state import GraphState
from agents.reflector import reflector_node


async def build_state(
    last_status="success",
    last_action="ping.icmp",
    last_error="",
    plan=None,
    current_step=0,
    summaries=None,
):
    state = GraphState(
        last_status=last_status,
        last_action=last_action,
        last_error=last_error,
        plan=plan or [{"action": "ping.icmp", "params": {"target": "localhost"}}],
        current_step=current_step,
        summaries=summaries or [],
    )
    return await reflector_node(state)


class TestReflectorNode:
    async def test_success_advances_step(self):
        plan = [
            {"action": "ping.icmp", "params": {"target": "h1"}},
            {"action": "disk.usage", "params": {}},
        ]
        state = await build_state(plan=plan, current_step=0)
        assert state.current_step == 1  # advanced by one
        assert state.last_status == "success"

    async def test_success_on_last_step_sets_conclusion(self):
        state = await build_state(plan=[{"action": "ping.icmp", "params": {}}], current_step=0)
        # After success: advance to step 1, plan length is 1 → done
        assert state.current_step == 1
        assert state.conclusion == "All steps completed successfully"

    async def test_cycle_detected_after_three_same_failures(self):
        summaries = [
            "FAIL:ping.icmp error=TIMEOUT → retry",
            "FAIL:ping.icmp error=TIMEOUT → retry",
            "FAIL:ping.icmp error=TIMEOUT → retry",
        ]
        state = await build_state(
            last_status="failure",
            last_action="ping.icmp",
            last_error="TIMEOUT",
            summaries=summaries,
        )
        assert state.cycle_detected is True
        assert state.needs_human is True
        assert "Cycle detected" in state.conclusion

    async def test_total_retries_exceeded(self):
        summaries = ["FAIL:action1 error=E1 → retry"] * 5
        state = await build_state(
            last_status="failure",
            last_action="ping.icmp",
            last_error="TIMEOUT",
            summaries=summaries,
        )
        assert state.needs_human is True
        assert "Total retries" in state.conclusion

    async def test_replan_clears_plan(self):
        state = await build_state(
            last_status="failure",
            last_action="ping.icmp",
            last_error="INVALID_PARAMS",
        )
        assert state.plan == []

    async def test_human_for_non_retryable(self):
        state = await build_state(
            last_status="failure",
            last_action="ping.icmp",
            last_error="TOOL_PANIC",
        )
        assert state.needs_human is True
        assert "Non-retryable" in state.conclusion
