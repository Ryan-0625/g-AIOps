"""Tests for OpenAIAdapter — chat, tool_calls, streaming, and error handling."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from llm.openai_adapter import OpenAIAdapter

# Sample messages for testing
SAMPLE_MESSAGES = [{"role": "user", "content": "Ping 10.0.0.1"}]
SAMPLE_TOOLS = [{
    "function": {
        "name": "ping.icmp",
        "description": "ICMP Ping",
        "parameters": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
}]


@pytest.fixture
def adapter():
    return OpenAIAdapter(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        timeout=30.0,
    )


class TestOpenAIAdapterChat:
    async def test_chat_success(self, adapter):
        """Successful chat should return message with content."""
        mock_completion = AsyncMock()
        mock_choice = Mock()
        mock_choice.message.content = "Pinging 10.0.0.1..."
        mock_choice.message.tool_calls = None
        mock_completion.choices = [mock_choice]

        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(return_value=mock_completion)):
            result = await adapter.chat(SAMPLE_MESSAGES)

        assert "message" in result
        assert result["message"]["content"] == "Pinging 10.0.0.1..."

    async def test_chat_tool_calls(self, adapter):
        """Chat with tools should return tool_calls in message."""
        mock_tool_call = Mock()
        mock_tool_call.function.name = "ping.icmp"
        mock_tool_call.function.arguments = '{"target": "10.0.0.1"}'

        mock_completion = AsyncMock()
        mock_choice = Mock()
        mock_choice.message.content = None
        mock_choice.message.tool_calls = [mock_tool_call]
        mock_completion.choices = [mock_choice]

        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(return_value=mock_completion)):
            result = await adapter.chat(SAMPLE_MESSAGES, tools=SAMPLE_TOOLS)

        assert "tool_calls" in result["message"]
        assert result["message"]["tool_calls"][0]["function"]["name"] == "ping.icmp"

    async def test_chat_timeout(self, adapter):
        """Timeout should return an error response."""
        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(side_effect=TimeoutError("Request timed out"))):
            result = await adapter.chat(SAMPLE_MESSAGES, timeout=1.0)

        assert "error" in result
        assert "OPENAI_ERROR" in result["error"]

    async def test_chat_connection_error(self, adapter):
        """Connection error should return an error response."""
        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(side_effect=ConnectionError("Connection refused"))):
            result = await adapter.chat(SAMPLE_MESSAGES)

        assert "error" in result
        assert "OPENAI_ERROR" in result["error"]

    async def test_chat_no_choices(self, adapter):
        """Empty choices list should return empty content."""
        mock_completion = AsyncMock()
        mock_completion.choices = []

        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(return_value=mock_completion)):
            result = await adapter.chat(SAMPLE_MESSAGES)

        assert result["message"]["content"] == ""


class TestOpenAIAdapterStream:
    async def test_chat_stream_yields_content_chunks(self, adapter):
        """Streaming should yield content chunks as they arrive."""
        mock_chunk_1 = Mock()
        mock_choice_1 = Mock()
        mock_delta_1 = Mock()
        mock_delta_1.content = "Pinging"
        mock_delta_1.tool_calls = None
        mock_choice_1.delta = mock_delta_1
        mock_chunk_1.choices = [mock_choice_1]

        mock_chunk_2 = Mock()
        mock_choice_2 = Mock()
        mock_delta_2 = Mock()
        mock_delta_2.content = " 10.0.0.1..."
        mock_delta_2.tool_calls = None
        mock_choice_2.delta = mock_delta_2
        mock_chunk_2.choices = [mock_choice_2]

        class AsyncIter:
            def __init__(self, chunks):
                self._chunks = chunks
            def __aiter__(self):
                return self._gen()
            async def _gen(self):
                for c in self._chunks:
                    yield c
        mock_stream = AsyncIter([mock_chunk_1, mock_chunk_2])

        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(return_value=mock_stream)):
            parts = []
            async for part in adapter.chat_stream(SAMPLE_MESSAGES):
                parts.append(part)

        assert len(parts) == 2
        assert parts[0]["content"] == "Pinging"
        assert parts[1]["content"] == " 10.0.0.1..."

    async def test_chat_stream_error(self, adapter):
        """Stream error should yield an error chunk."""
        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(side_effect=RuntimeError("Stream failed"))):
            parts = []
            async for part in adapter.chat_stream(SAMPLE_MESSAGES):
                parts.append(part)

        assert len(parts) == 1
        assert "error" in parts[0]

    async def test_chat_stream_tool_calls(self, adapter):
        """Streaming with tool_calls should yield function chunks."""
        mock_tc = Mock()
        mock_tc.function.name = "ping.icmp"
        mock_tc.function.arguments = '{"target":'

        mock_chunk = Mock()
        mock_choice = Mock()
        mock_delta = Mock()
        mock_delta.content = None
        mock_delta.tool_calls = [mock_tc]
        mock_choice.delta = mock_delta
        mock_chunk.choices = [mock_choice]

        class AsyncIter:
            def __init__(self, chunks):
                self._chunks = chunks
            def __aiter__(self):
                return self._gen()
            async def _gen(self):
                for c in self._chunks:
                    yield c
        mock_stream = AsyncIter([mock_chunk])

        with patch.object(adapter.client.chat.completions, "create",
                          AsyncMock(return_value=mock_stream)):
            parts = []
            async for part in adapter.chat_stream(SAMPLE_MESSAGES, tools=SAMPLE_TOOLS):
                parts.append(part)

        assert len(parts) == 1
        assert "tool_calls" in parts[0]
        assert parts[0]["tool_calls"][0]["function"]["name"] == "ping.icmp"


class TestOpenAIAdapterClose:
    async def test_close_calls_client_close(self, adapter):
        """close() should call the underlying client's close method."""
        with patch.object(adapter.client, "close", AsyncMock()) as mock_close:
            await adapter.close()
            mock_close.assert_called_once()
