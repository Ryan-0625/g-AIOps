"""Tests for error_classifier — error code strategy classification."""

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
