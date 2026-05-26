"""Tests for error_classifier — error code strategy classification (v2.0 extended)."""
from safety.error_classifier import classify, is_retryable


class TestErrorClassifier:
    def test_retryable_codes(self):
        for code in ["EXECUTION_TIMEOUT", "CONNECTION_RESET", "WORKER_OFFLINE", "TTL_EXPIRED"]:
            assert classify(code) == "retry", f"{code} should be retry"
            assert is_retryable(code) is True, f"{code} should be retryable"

    def test_replan_codes(self):
        for code in ["INVALID_ARGS", "COMMAND_NOT_ALLOWED", "UNKNOWN_TOOL", "PARAM_SANITIZED"]:
            assert classify(code) == "replan", f"{code} should be replan"
            assert is_retryable(code) is False, f"{code} should not be retryable"

    def test_human_codes(self):
        for code in ["TOOL_PANIC", "WORKER_ID_CONFLICT", "AUTH_FAILED", "BRAIN_CYCLE_DETECTED"]:
            assert classify(code) == "human", f"{code} should be human"
            assert is_retryable(code) is False, f"{code} should not be retryable"

    def test_non_error_codes(self):
        assert classify("OUTPUT_TOO_LARGE") == "non_error"

    def test_unknown_code_defaults_to_replan(self):
        assert classify("SOME_RANDOM_ERROR") == "replan"
        assert is_retryable("SOME_RANDOM_ERROR") is False

    def test_v2_retryable_dynamic_tool(self):
        for code in ["TOOL_DEPLOY_TIMEOUT", "BRAIN_STREAM_ERROR"]:
            assert classify(code) == "retry", f"{code} should be retry"

    def test_v2_replan_dynamic_tool(self):
        for code in ["TOOL_DEPLOY_FAILED", "TOOL_COMPILE_ERROR", "TOOL_MEMORY_LIMIT", "TOOL_RUNTIME_UNAVAILABLE", "PARAM_TOO_LONG"]:
            assert classify(code) == "replan", f"{code} should be replan"

    def test_v2_human_dynamic_tool(self):
        for code in ["TOOL_SANDBOX_VIOLATION", "BRAIN_CODE_GEN_FAILED", "MEMORY_RETRIEVAL_FAILED"]:
            assert classify(code) == "human", f"{code} should be human"

    def test_tool_deploy_timeout_retryable(self):
        assert is_retryable("TOOL_DEPLOY_TIMEOUT") is True

    def test_tool_compile_error_not_retryable(self):
        assert is_retryable("TOOL_COMPILE_ERROR") is False

    def test_tool_sandbox_violation_not_retryable(self):
        assert is_retryable("TOOL_SANDBOX_VIOLATION") is False

    def test_broadcast_partial_failure_non_error(self):
        assert classify("BROADCAST_PARTIAL_FAILURE") == "non_error"
