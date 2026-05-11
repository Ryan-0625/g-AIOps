"""Stream handler — collects streaming LLM responses with retry and JSON extraction."""

import json
from typing import Any, AsyncGenerator, Callable, Optional

from logger.structured_logger import get_logger

logger = get_logger()


class StreamHandler:
    """Collects a tool call from an LLM streaming response.

    Capabilities:
    - Buffers chunks until a complete tool_call JSON is found.
    - Retries once on connection error.
    - Extracts the first { ... } JSON block from the buffer.
    """

    def __init__(self, max_retries: int = 1):
        self.max_retries = max_retries
        self._buffer = ""

    async def collect_tool_call(
        self,
        stream_factory: Callable[[], AsyncGenerator[dict[str, Any], None]],
    ) -> Optional[str]:
        """Collect the first complete tool_call JSON from a stream.

        Retries up to `max_retries` times on connection errors.
        Returns None if all retries fail or no tool call is found.
        """
        for attempt in range(self.max_retries + 1):
            try:
                async for chunk in stream_factory():
                    self._buffer += json.dumps(chunk)
                    extracted = self._extract_json()
                    if extracted:
                        return extracted
            except (ConnectionError, TimeoutError) as e:
                if attempt < self.max_retries:
                    logger.warning(f"stream retry {attempt + 1}/{self.max_retries}")
                    continue
                logger.error(f"stream failed after {self.max_retries} retries")
                return None

            # Check if buffer has anything useful even without clear JSON.
            if self._buffer.strip():
                return self._buffer

            return None

    def _extract_json(self) -> Optional[str]:
        """Find the first complete JSON object in the buffer."""
        depth = 0
        start = -1
        for i, ch in enumerate(self._buffer):
            if ch == "{":
                if start == -1:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    candidate = self._buffer[start : i + 1]
                    self._buffer = self._buffer[i + 1 :]
                    return candidate
        return None
