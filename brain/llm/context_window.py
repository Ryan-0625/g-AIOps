"""Sliding window context management to prevent token explosion."""

from typing import Any

MAX_STEPS = 5
MAX_TOKENS = 32_000


def compress_messages(
    messages: list[dict[str, Any]],
    summaries: list[str],
    max_tokens: int = MAX_TOKENS,
) -> list[dict[str, Any]]:
    """Compress message list for LLM context window.

    Strategy:
    - Keep system prompt (first message).
    - Keep the most recent MAX_STEPS messages in full.
    - Replace older messages with a text summary.
    """
    if not messages:
        return []

    # Keep system prompt.
    result: list[dict[str, Any]] = []
    if messages[0]["role"] == "system":
        result.append(messages[0])

    if len(messages) > MAX_STEPS + 1:
        # Compress history into summary.
        history = summaries[:-MAX_STEPS] if len(summaries) > MAX_STEPS else []
        if history:
            result.append({
                "role": "system",
                "content": f"[History summary, {len(history)} steps]:\n" + "\n".join(history),
            })
        result.extend(messages[-MAX_STEPS:])
    else:
        result.extend(messages[1:] if messages[0]["role"] == "system" else messages)

    return result
