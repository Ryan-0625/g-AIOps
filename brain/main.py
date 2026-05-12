"""
gAIOps Brain - Decision Engine Entry Point

Initializes LLM adapter, Master client, and the LangGraph execution engine.
Listens for signals and keeps the event loop alive.
"""

import asyncio
import os
import signal
import sys

from aiohttp import web

from config import BrainConfig
from core.graph import GraphEngine
from llm.adapter import LLMAdapter
from llm.ollama_adapter import OllamaAdapter
from llm.openai_adapter import OpenAIAdapter
from tools.master_client import MasterClient
from logger.structured_logger import get_logger
from intent.classifier import IntentClassifier, IntentCategory, IntentResult
from logger.trace_context import generate_trace_id

logger = get_logger()
engine: GraphEngine | None = None
_intent_classifier = IntentClassifier()


async def main() -> None:
    global engine
    logger.info("Brain starting", extra={"data": {"pid": os.getpid()}})

    cfg = BrainConfig.from_env()

    # Initialize LLM based on configured provider.
    llm: LLMAdapter
    provider = cfg.llm_provider.lower()
    if provider == "ollama":
        llm = OllamaAdapter(
            base_url=cfg.llm_base_url,
            model=cfg.llm_model,
            timeout=cfg.llm_timeout,
        )
    elif provider == "openai":
        llm = OpenAIAdapter(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", cfg.llm_model),
            timeout=cfg.llm_timeout,
        )
    else:
        logger.warning(f"Unknown LLM provider {provider!r}, falling back to Ollama")
        llm = OllamaAdapter(
            base_url=cfg.llm_base_url,
            model=cfg.llm_model,
            timeout=cfg.llm_timeout,
        )

    # Initialize Master API client.
    master = MasterClient(
        api_url=cfg.master_api_url,
        cluster_token=cfg.cluster_token,
        timeout=cfg.master_request_timeout,
        tls_verify=cfg.tls_verify,
    )

    # Initialize graph engine.
    engine = GraphEngine(llm=llm, master=master, read_only=cfg.read_only)

    logger.info("Brain initialized", extra={"data": {
        "llm_provider": cfg.llm_provider,
        "llm_model": cfg.llm_model,
        "llm_base_url": cfg.llm_base_url,
        "master_api_url": cfg.master_api_url,
    }})

    # Signal handling.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: _shutdown(s))

    logger.info("Brain ready — awaiting triggers")

    # HTTP health endpoint.
    health_app = web.Application()

    async def health_handler(request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "uptime": int(asyncio.get_event_loop().time()),
            "pid": os.getpid(),
            "degraded": engine.is_degraded if engine else False,
        })

    async def _fast_health(master: MasterClient) -> web.Response:
        """Fast-path: return cluster health without LLM."""
        tid = generate_trace_id()
        try:
            workers = await master.list_workers()
            num_workers = len(workers)
            return web.json_response({
                "trace_id": tid,
                "status": "completed",
                "conclusion": f"Cluster is healthy. {num_workers} worker(s) connected.",
                "fast_path": True,
                "data": {"workers_count": num_workers, "workers": workers},
            })
        except Exception as e:
            return web.json_response({
                "trace_id": tid,
                "status": "failed",
                "conclusion": f"Health check failed: {e}",
                "fast_path": True,
            })

    async def _fast_workers(master: MasterClient) -> web.Response:
        """Fast-path: list workers without LLM."""
        tid = generate_trace_id()
        try:
            workers = await master.list_workers()
            if not workers:
                return web.json_response({
                    "trace_id": tid,
                    "status": "completed",
                    "conclusion": "No workers connected.",
                    "fast_path": True,
                    "data": {"workers": []},
                })
            lines = []
            for w in workers:
                wid = w.get("worker_id", "?")
                load = f"{w.get('current_load', 0)}/{w.get('max_concurrent', 1)}"
                actions = ", ".join(w.get("actions", [])[:6])
                lines.append(f"  {wid}  [{load}]  {actions}")
            conclusion = f"{len(workers)} worker(s) connected:\n" + "\n".join(lines)
            return web.json_response({
                "trace_id": tid,
                "status": "completed",
                "conclusion": conclusion,
                "fast_path": True,
                "data": {"workers": workers},
            })
        except Exception as e:
            return web.json_response({
                "trace_id": tid,
                "status": "failed",
                "conclusion": f"Failed to list workers: {e}",
                "fast_path": True,
            })

    async def _fast_tool(master: MasterClient, intent: IntentResult) -> web.Response:
        """Fast-path: execute a single tool without LLM."""
        tid = generate_trace_id()
        try:
            result = await master.execute(
                action=intent.tool_name,
                params=intent.params or {},
                trace_id=tid,
            )
            resp_status = result.get("status", "failure")
            err = result.get("error", {})
            err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            if resp_status == "success":
                conclusion = f"Executed {intent.tool_name} successfully."
            elif err_msg:
                conclusion = f"{intent.tool_name}: {err_msg}"
            else:
                conclusion = f"{intent.tool_name}: {resp_status}"
            return web.json_response({
                "trace_id": tid,
                "status": "completed" if resp_status != "failure" else "failed",
                "conclusion": conclusion,
                "fast_path": True,
                "tool": intent.tool_name,
                "params": intent.params,
                "data": result.get("data", {}),
            })
        except Exception as e:
            return web.json_response({
                "trace_id": tid,
                "status": "failed",
                "conclusion": f"Tool execution error: {e}",
                "fast_path": True,
                "tool": intent.tool_name,
            })

    async def chat_handler(request: web.Request) -> web.Response:
        """Accept a natural language message and return the Brain's response."""
        global engine
        if not engine:
            return web.json_response({"error": "Brain not initialized"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        message = (body.get("message") or "").strip()
        if not message:
            return web.json_response({"error": "message is required"}, status=400)

        logger.info("Chat request", extra={"data": {"message": message[:100]}})

        # ── Fast-path: intent classification (zero LLM cost) ────────
        intent = _intent_classifier.classify(message)

        if intent.category == IntentCategory.IRRELEVANT:
            return web.json_response({
                "trace_id": generate_trace_id(),
                "status": "rejected",
                "conclusion": intent.reason or "Message rejected.",
                "fast_path": True,
            })

        if intent.category == IntentCategory.HEALTH:
            return await _fast_health(master)

        if intent.category == IntentCategory.WORKERS:
            return await _fast_workers(master)

        if intent.category == IntentCategory.TOOL:
            return await _fast_tool(master, intent)

        # intent.category == COMPLEX → proceed to LLM pipeline.
        trace_id = await engine.start_session(message)

        # Wait for completion with timeout.
        task = engine.active_sessions.get(trace_id)
        if task:
            try:
                await asyncio.wait_for(task, timeout=180.0)
            except asyncio.TimeoutError:
                return web.json_response({
                    "trace_id": trace_id,
                    "status": "running",
                    "conclusion": "Still processing — check later.",
                })

        result = engine.pop_session_result(trace_id) or {
            "trace_id": trace_id,
            "status": "not_found",
            "conclusion": "Session not found.",
        }
        return web.json_response(result)

    health_app.router.add_get("/health", health_handler)
    health_app.router.add_post("/api/chat", chat_handler)
    health_runner = web.AppRunner(health_app)
    await health_runner.setup()
    health_site = web.TCPSite(health_runner, "0.0.0.0", 9091)
    await health_site.start()
    logger.info("Health endpoint listening", extra={"data": {"addr": "0.0.0.0:9091"}})

    # Keep alive indefinitely.
    await asyncio.Event().wait()


def _shutdown(sig: signal.Signals) -> None:
    logger.info("Brain shutting down", extra={"data": {"signal": sig.name}})
    if engine:
        for _, task in list(engine.active_sessions.items()):
            task.cancel()
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT)
