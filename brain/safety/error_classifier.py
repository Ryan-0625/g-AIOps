"""Classify error codes into retry / replan / human strategies."""

STRATEGIES: dict[str, set[str]] = {
    "retry": {
        "EXECUTION_TIMEOUT", "CONNECTION_RESET", "WORKER_OFFLINE",
        "TTL_EXPIRED", "NO_AVAILABLE_WORKER", "SHUTTING_DOWN",
        "WORKER_OVERLOAD", "MASTER_OVERLOAD",
    },
    "replan": {
        "INVALID_ARGS", "COMMAND_NOT_ALLOWED", "PATH_NOT_ALLOWED",
        "SERVICE_NOT_FOUND", "SERVICE_ALREADY_RUNNING", "PING_FAILED",
        "PROCESS_NOT_FOUND", "APPROVAL_TIMEOUT", "UNKNOWN_TOOL",
        "PARAM_SANITIZED", "MISSING_TRACE_ID", "MISSING_ACTION",
        "INVALID_ENVELOPE", "PARAM_MISSING", "INVALID_PARAMS",
    },
    "human": {
        "TOOL_PANIC", "DISK_READ_ERROR", "WORKER_ID_CONFLICT",
        "APPROVAL_REJECTED", "BRAIN_LLM_UNAVAILABLE",
        "BRAIN_CYCLE_DETECTED", "BRAIN_CONTEXT_OVERFLOW",
        "PROTO_VERSION_MISMATCH", "AUTH_FAILED", "AUTH_TOKEN_MISSING",
    },
}

NON_ERROR = {
    "OUTPUT_TOO_LARGE", "BROADCAST_PARTIAL_FAILURE",
}


def classify(error_code: str) -> str:
    """Return 'retry', 'replan', 'human', or 'non_error'."""
    for strategy, codes in STRATEGIES.items():
        if error_code in codes:
            return strategy
    if error_code in NON_ERROR:
        return "non_error"
    return "replan"  # Conservative default.


def is_retryable(error_code: str) -> bool:
    return classify(error_code) == "retry"
