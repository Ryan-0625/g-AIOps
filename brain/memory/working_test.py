"""Tests for the Working Memory module."""

import pytest
from memory.working import WorkingMemory


@pytest.fixture
def wm():
    return WorkingMemory(trace_id="test-123", goal="check disk usage")


class TestWorkingMemory:
    def test_init(self, wm):
        assert wm.trace_id == "test-123"
        assert wm.goal == "check disk usage"
        assert len(wm.react_trajectory) == 0
        assert len(wm.variables) == 0

    def test_add_react_step(self, wm):
        wm.add_react_step(
            thought="I need to check disk",
            action="disk.usage",
            observation={"status": "success", "data": {"usage_pct": "75.2"}},
        )
        assert len(wm.react_trajectory) == 1
        assert wm.react_trajectory[0]["action"] == "disk.usage"

    def test_max_trajectory(self, wm):
        wm.max_trajectory = 3
        for i in range(5):
            wm.add_react_step(
                thought=f"step {i}",
                action=f"tool.{i}",
                observation={"status": "success"},
            )
        assert len(wm.react_trajectory) == 3
        # Should keep the most recent 3
        assert wm.react_trajectory[0]["action"] == "tool.2"
        assert wm.react_trajectory[-1]["action"] == "tool.4"

    def test_variables(self, wm):
        wm.set_variable("disk_usage", "85%")
        wm.set_variable("target_path", "/data")

        assert wm.get_variable("disk_usage") == "85%"
        assert wm.get_variable("target_path") == "/data"
        assert wm.get_variable("nonexistent") is None
        assert wm.get_variable("nonexistent", "default") == "default"

    def test_get_recent_trajectory(self, wm):
        for i in range(5):
            wm.add_react_step(
                thought=f"step {i}",
                action=f"tool.{i}",
                observation={"status": "success"},
            )
        recent = wm.get_recent_trajectory(2)
        assert len(recent) == 2
        assert recent[0]["action"] == "tool.3"
        assert recent[1]["action"] == "tool.4"

    def test_format_trajectory_for_prompt(self, wm):
        wm.add_react_step(
            thought="check disk",
            action="disk.usage",
            observation={"status": "success", "data": {"usage_pct": "80"}},
        )
        formatted = wm.format_trajectory_for_prompt()
        assert "check disk" in formatted
        assert "disk.usage" in formatted
        assert "success" in formatted

    def test_empty_trajectory_format(self, wm):
        formatted = wm.format_trajectory_for_prompt()
        assert formatted == ""
