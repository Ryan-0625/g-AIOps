"""Reflector node — evaluates execution results, detects loops, decides next action."""

from core.state import GraphState
from safety.error_classifier import classify
from logger.structured_logger import get_logger

logger = get_logger()

MAX_RETRY_SAME = 3
MAX_TOTAL_RETRIES = 5


async def reflector_node(state: GraphState) -> GraphState:
    """Evaluate the last execution result and decide next step.

    Returned state.action determines the graph routing:
    - "continue"  → execute next step in plan
    - "retry"     → retry current step
    - "replan"    → go back to planner (current plan is invalid)
    - "human"     → escalate to human intervention
    """
    if state.last_status == "success":
        state.add_summary(f"Step {state.current_step} OK: {state.last_action}")
        state.advance()

        if state.is_done():
            state.conclusion = "All steps completed successfully"
            state.add_summary(state.conclusion)
        return state

    # Failure analysis.
    error_code = state.last_error or "UNKNOWN"

    # Cycle detection: same action + same error repeatedly.
    same_failures = 0
    for s in reversed(state.summaries[-5:]):
        if f"FAIL:{state.last_action}" in s:
            same_failures += 1
        else:
            break

    if same_failures >= MAX_RETRY_SAME:
        state.cycle_detected = True
        state.needs_human = True
        state.conclusion = (
            f"Cycle detected: {state.last_action} failed {same_failures}x "
            f"with error [{error_code}]. Escalating to human."
        )
        logger.warning("Cycle detected", extra={"error_code": "BRAIN_CYCLE_DETECTED"})
        return state

    total_retries = sum(1 for s in state.summaries if "FAIL:" in s)
    if total_retries >= MAX_TOTAL_RETRIES:
        state.needs_human = True
        state.conclusion = f"Total retries ({total_retries}) exceeded limit. Escalating."
        return state

    strategy = classify(error_code)

    if strategy == "retry":
        state.add_summary(f"FAIL:{state.last_action} error={error_code} → retry")
        state.advance()
    elif strategy == "replan":
        state.add_summary(f"FAIL:{state.last_action} error={error_code} → replan")
        state.plan = []  # Clear plan for regeneration.
    else:  # human
        state.needs_human = True
        state.conclusion = f"Non-retryable error {error_code}: {state.last_error}"
        state.add_summary(state.conclusion)

    return state
