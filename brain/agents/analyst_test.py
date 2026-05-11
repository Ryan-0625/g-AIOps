"""Tests for analyst_node — LLM path, fallback, and edge cases."""

import pytest

from agents.analyst import analyst_node
from core.state import GraphState
from llm.adapter import LLMAdapter


class FakeAnalystLLM(LLMAdapter):
    """Controlled fake LLM for analyst testing."""

    def __init__(self, response: dict | None = None, fail: bool = False):
        self.response = response
        self.fail = fail
        self.calls = []

    async def chat(self, messages, tools=None, timeout=30.0) -> dict | None:
        self.calls.append({"messages": messages, "tools": tools})
        if self.fail:
            raise RuntimeError("LLM unavailable")
        if self.response is None:
            return None
        return self.response

    async def chat_stream(self, messages, tools=None):
        yield {"error": "not implemented"}

    async def close(self):
        pass


class TestAnalystNode:
    async def test_llm_success_injects_summary(self):
        """LLM success should create an analysis summary."""
        llm = FakeAnalystLLM(response={
            "message": {"content": "The user wants to check disk usage on the server."},
        })
        state = GraphState(trace_id="analyst-test-1")
        result = await analyst_node(state, "Check disk usage on server", llm)

        assert len(result.summaries) == 1
        assert "Analysis:" in result.summaries[0]
        assert "disk" in result.summaries[0].lower()

    async def test_llm_failure_fallback(self):
        """LLM failure should trigger keyword-based fallback."""
        llm = FakeAnalystLLM(fail=True)
        state = GraphState(trace_id="analyst-test-2")
        result = await analyst_node(state, "Check disk usage on server", llm)

        assert len(result.summaries) == 1
        assert "Analysed:" in result.summaries[0]
        assert "disk" in result.summaries[0]

    async def test_llm_none_response_fallback(self):
        """LLM returning None should trigger fallback."""
        llm = FakeAnalystLLM(response=None)
        state = GraphState(trace_id="analyst-test-3")
        result = await analyst_node(state, "Ping 10.0.0.1", llm)

        assert len(result.summaries) == 1
        assert "ping" in result.summaries[0].lower()

    async def test_empty_context_safe_skip(self):
        """Empty context should not crash and produce a fallback summary."""
        llm = FakeAnalystLLM(response=None)
        state = GraphState(trace_id="analyst-test-4")
        result = await analyst_node(state, "", llm)

        assert len(result.summaries) == 1
        assert "empty" in result.summaries[0]

    async def test_no_llm_keyword_fallback(self):
        """Without LLM, analyst should use keyword matching."""
        state = GraphState(trace_id="analyst-test-5")
        result = await analyst_node(state, "Restart nginx service", None)

        assert len(result.summaries) == 1
        assert "manage service" in result.summaries[0]

    async def test_disk_keyword_triggers_check_disk(self):
        """'disk' keyword should map to 'check disk usage' intent."""
        state = GraphState(trace_id="analyst-test-6")
        result = await analyst_node(state, "How much disk space is left?", None)

        assert "check disk usage" in result.summaries[0]

    async def test_ping_keyword_triggers_network(self):
        """'ping' keyword should map to 'check network connectivity' intent."""
        state = GraphState(trace_id="analyst-test-7")
        result = await analyst_node(state, "Ping the gateway", None)

        assert "check network" in result.summaries[0]

    async def test_service_keyword_triggers_manage_service(self):
        """'service' keyword should map to 'manage service' intent."""
        state = GraphState(trace_id="analyst-test-8")
        result = await analyst_node(state, "Restart the sshd service", None)

        assert "manage service" in result.summaries[0]

    async def test_log_keyword_triggers_inspect_logs(self):
        """'log' keyword should map to 'inspect logs' intent."""
        state = GraphState(trace_id="analyst-test-9")
        result = await analyst_node(state, "Show me the syslog", None)

        assert "inspect logs" in result.summaries[0]
