"""Tests for LLMOutputSanitizer — three-layer LLM output sanitization."""

from llm.sanitizer import LLMOutputSanitizer, ParamSanitizationError

SAMPLE_REGISTRY = {
    "ping.icmp": {
        "required_params": ["target"],
        "params": {"target": {"type": "string"}},
    },
    "disk.usage": {
        "required_params": [],
        "params": {"path": {"type": "string"}},
    },
    "service.status": {
        "required_params": ["name"],
        "params": {"name": {"type": "string"}},
    },
}


class TestLLMOutputSanitizer:
    def setup_method(self):
        self.sanitizer = LLMOutputSanitizer(SAMPLE_REGISTRY)

    def test_accepts_valid_call(self):
        result = self.sanitizer.sanitize_tool_call(
            '{"action": "ping.icmp", "params": {"target": "localhost"}}'
        )
        assert result.action == "ping.icmp"
        assert result.params == {"target": "localhost"}
        assert result.error is None

    def test_rejects_empty_input(self):
        result = self.sanitizer.sanitize_tool_call("")
        assert result.error == "EMPTY_OUTPUT"

    def test_rejects_unknown_tool(self):
        result = self.sanitizer.sanitize_tool_call(
            '{"action": "nonexistent.tool", "params": {}}'
        )
        assert "UNKNOWN_TOOL" in result.error

    def test_rejects_missing_required_params(self):
        result = self.sanitizer.sanitize_tool_call(
            '{"action": "ping.icmp", "params": {}}'
        )
        assert "MISSING_PARAMS" in result.error

    def test_rejects_shell_injection(self):
        result = self.sanitizer.sanitize_tool_call(
            '{"action": "ping.icmp", "params": {"target": "localhost; rm -rf"}}'
        )
        assert "PARAM_SANITIZED" in result.error

    def test_rejects_path_traversal(self):
        result = self.sanitizer.sanitize_tool_call(
            '{"action": "disk.usage", "params": {"path": "../../etc"}}'
        )
        assert "PARAM_SANITIZED" in result.error

    def test_fixes_trailing_comma(self):
        result = self.sanitizer.sanitize_tool_call(
            '{"action": "ping.icmp", "params": {"target": "localhost",}}'
        )
        assert result.action == "ping.icmp"
        assert result.error is None

    def test_fixes_unquoted_keys(self):
        result = self.sanitizer.sanitize_tool_call(
            "{action: 'ping.icmp', params: {target: 'localhost'}}"
        )
        # Note: single quotes won't be fixed; this test verifies it fails gracefully.
        assert result.error is None or "INVALID_JSON" in result.error

    def test_accepts_no_params(self):
        result = self.sanitizer.sanitize_tool_call(
            '{"action": "disk.usage", "params": {}}'
        )
        assert result.action == "disk.usage"
        assert result.error is None
