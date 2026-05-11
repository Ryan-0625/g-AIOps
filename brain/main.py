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

logger = get_logger()
engine: GraphEngine | None = None


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

    health_app.router.add_get("/health", health_handler)
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
