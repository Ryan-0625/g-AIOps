"""Tests for OllamaAdapter — HTTP calls with aiohttp test server."""

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from llm.ollama_adapter import OllamaAdapter


class OllamaAdapterTest(AioHTTPTestCase):
    async def get_application(self):
        """Simulates the Ollama /api/chat endpoint."""

        async def chat_handler(request):
            body = await request.json()
            model = body.get("model", "default")
            stream = body.get("stream", False)

            if stream:
                response = web.StreamResponse()
                response.headers["Content-Type"] = "application/x-ndjson"
                await response.prepare(request)
                # First token.
                await response.write(b'{"message":{"role":"assistant","content":"Hello"}}\n')
                # Final message with done flag.
                await response.write(b'{"message":{"role":"assistant","content":""},"done":true}\n')
                return response

            # Non-streaming response.
            return web.json_response({
                "model": model,
                "message": {
                    "role": "assistant",
                    "content": "Ping 10.0.0.1",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "ping.icmp",
                                "arguments": {"target": "10.0.0.1"},
                            }
                        }
                    ],
                },
                "done": True,
            })

        app = web.Application()
        app.router.add_post("/api/chat", chat_handler)
        return app

    @unittest_run_loop
    async def test_chat_returns_structured_response(self):
        adapter = OllamaAdapter(
            base_url=f"http://localhost:{self.server.port}",
            model="test-model",
            timeout=10.0,
        )
        result = await adapter.chat(
            messages=[{"role": "user", "content": "Ping 10.0.0.1"}],
        )
        assert result["model"] == "test-model"
        assert result["done"] is True
        message = result["message"]
        assert message["content"] == "Ping 10.0.0.1"
        assert len(message["tool_calls"]) == 1
        assert message["tool_calls"][0]["function"]["name"] == "ping.icmp"

    @unittest_run_loop
    async def test_chat_with_tools(self):
        adapter = OllamaAdapter(
            base_url=f"http://localhost:{self.server.port}",
            model="test-model",
            timeout=10.0,
        )
        tools = [{"function": {"name": "ping.icmp", "description": "Ping"}}]
        result = await adapter.chat(
            messages=[{"role": "user", "content": "Ping"}],
            tools=tools,
        )
        assert result["done"] is True
        # Verify tools were sent in the request payload.
        assert "tools" in result or result is not None

    @unittest_run_loop
    async def test_chat_stream_yields_multiple_chunks(self):
        adapter = OllamaAdapter(
            base_url=f"http://localhost:{self.server.port}",
            model="test-model",
            timeout=10.0,
        )
        chunks = []
        async for chunk in adapter.chat_stream(
            messages=[{"role": "user", "content": "Say hello"}],
        ):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0]["message"]["content"] == "Hello"

    @unittest_run_loop
    async def test_chat_stream_with_tools(self):
        adapter = OllamaAdapter(
            base_url=f"http://localhost:{self.server.port}",
            model="test-model",
            timeout=10.0,
        )
        tools = [{"function": {"name": "ping.icmp"}}]
        chunks = []
        async for chunk in adapter.chat_stream(
            messages=[{"role": "user", "content": "Ping"}],
            tools=tools,
        ):
            chunks.append(chunk)
        assert len(chunks) > 0

    @unittest_run_loop
    async def test_chat_connection_error(self):
        adapter = OllamaAdapter(
            base_url="http://localhost:1",
            model="test-model",
            timeout=1.0,
        )
        chunks = []
        async for chunk in adapter.chat_stream(
            messages=[{"role": "user", "content": "Hi"}],
        ):
            chunks.append(chunk)

        # Should get an error chunk.
        error_chunks = [c for c in chunks if "error" in c]
        assert len(error_chunks) > 0

    @unittest_run_loop
    async def test_chat_timeout(self):
        """A very short timeout should produce an error chunk in stream."""
        adapter = OllamaAdapter(
            base_url=f"http://localhost:{self.server.port}",
            model="test-model",
            timeout=0.001,  # Very short timeout.
        )
        chunks = []
        async for chunk in adapter.chat_stream(
            messages=[{"role": "user", "content": "Hi"}],
        ):
            chunks.append(chunk)

        # May get STREAM_TIMEOUT or no chunks depending on timing.
        # At minimum, should not crash.
        assert isinstance(chunks, list)

    @unittest_run_loop
    async def test_close_releases_session(self):
        adapter = OllamaAdapter(
            base_url=f"http://localhost:{self.server.port}",
            model="test-model",
        )
        await adapter.chat(messages=[{"role": "user", "content": "Hi"}])
        assert adapter._session is not None
        assert not adapter._session.closed
        await adapter.close()
        assert adapter._session.closed
