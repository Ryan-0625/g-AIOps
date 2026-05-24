"""
gAIOps Brain - Decision Engine Entry Point

Initializes LLM adapter, Master client, and the LangGraph execution engine.
Listens for signals and keeps the event loop alive.
"""

import asyncio
import os
import re
import signal
import sys
import time

import aiohttp
from aiohttp import web, hdrs

from config import BrainConfig
from core.graph import GraphEngine
from llm.adapter import LLMAdapter
from llm.ollama_adapter import OllamaAdapter
from llm.openai_adapter import OpenAIAdapter
from tools.master_client import MasterClient
from logger.structured_logger import get_logger
from agents.router import Router, RouterCategory, RouterResult
from logger.trace_context import generate_trace_id


def _fmt_duration(seconds: int) -> str:
    """Format seconds to short human string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}秒"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分"
    hours = minutes // 60
    days = hours // 24
    if days:
        return f"{days}天{hours % 24}小时"
    return f"{hours}小时{minutes % 60}分"


def _fmt_bytes(n) -> str:
    """Format byte count to human string."""
    try:
        n = int(n)
    except (ValueError, TypeError):
        return str(n)
    if n >= 1 << 40:
        return f"{n / (1 << 40):.1f}TB"
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f}GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f}MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.1f}KB"
    return f"{n}B"


class _RateLimiter:
    """Sliding-window rate limiter per client IP."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clients: dict[str, list[float]] = {}

    def allow(self, client_ip: str) -> bool:
        now = asyncio.get_event_loop().time()
        window_start = now - self.window_seconds
        timestamps = self._clients.get(client_ip, [])
        # Prune old entries.
        timestamps = [t for t in timestamps if t > window_start]
        if len(timestamps) >= self.max_requests:
            self._clients[client_ip] = timestamps
            return False
        timestamps.append(now)
        self._clients[client_ip] = timestamps
        return True


def _extract_bearer(request):
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get(hdrs.AUTHORIZATION, '')
    m = re.match(r'^Bearer\s+(.+)$', auth)
    return m.group(1) if m else None


def _authenticate(token, expected):
    """Constant-time comparison to prevent timing attacks."""
    if not token or not expected:
        return False
    if len(token) != len(expected):
        return False
    result = 0
    for a, b in zip(token, expected):
        result |= ord(a) ^ ord(b)
    return result == 0


logger = get_logger()
engine: GraphEngine | None = None
router: Router | None = None
health_runner: web.AppRunner | None = None
_shutting_down = False


class BrainMetrics:
    """Simple Prometheus-style metrics counters for the Brain."""
    def __init__(self):
        self.requests_total = 0
        self.requests_success = 0
        self.requests_failed = 0
        self.llm_calls_total = 0
        self.llm_errors_total = 0
        self.start_time = time.monotonic()

    def render_prometheus(self) -> str:
        uptime = int(time.monotonic() - self.start_time)
        return (
            "# HELP brain_requests_total Total requests processed\n"
            "# TYPE brain_requests_total counter\n"
            f"brain_requests_total {self.requests_total}\n"
            "# HELP brain_requests_success_total Successful requests\n"
            "# TYPE brain_requests_success_total counter\n"
            f"brain_requests_success_total {self.requests_success}\n"
            "# HELP brain_requests_failed_total Failed requests\n"
            "# TYPE brain_requests_failed_total counter\n"
            f"brain_requests_failed_total {self.requests_failed}\n"
            "# HELP brain_llm_calls_total Total LLM calls made\n"
            "# TYPE brain_llm_calls_total counter\n"
            f"brain_llm_calls_total {self.llm_calls_total}\n"
            "# HELP brain_llm_errors_total LLM call errors\n"
            "# TYPE brain_llm_errors_total counter\n"
            f"brain_llm_errors_total {self.llm_errors_total}\n"
            "# HELP brain_uptime_seconds Process uptime\n"
            "# TYPE brain_uptime_seconds gauge\n"
            f"brain_uptime_seconds {uptime}\n"
        )


metrics = BrainMetrics()


async def main() -> None:
    global engine, router
    logger.info("Brain starting", extra={"data": {"pid": os.getpid()}})

    cfg = BrainConfig.load("/app/brain.yaml")
    rate_limiter = _RateLimiter(max_requests=cfg.api_rate_limit, window_seconds=60)

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

    # Initialize intent router.
    router = Router(llm=llm)

    # Initialize graph engine.
    engine = GraphEngine(llm=llm, master=master, read_only=cfg.read_only, llm_max_retries=cfg.llm_max_retries, metrics=metrics)

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
        if _shutting_down:
            return web.json_response({"status": "shutting_down"}, status=503)
        # Check upstream Master connectivity.
        master_ok = False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{cfg.master_api_url}/health", timeout=2.0) as resp:
                    master_ok = resp.status == 200
        except Exception:
            pass
        return web.json_response({
            "status": "ok",
            "uptime": int(asyncio.get_event_loop().time()),
            "pid": os.getpid(),
            "degraded": engine.is_degraded if engine else False,
            "dependencies": {
                "master": "reachable" if master_ok else "unreachable",
            },
        })

    async def metrics_handler(request: web.Request) -> web.Response:
        return web.Response(text=metrics.render_prometheus(), content_type="text/plain; charset=utf-8")

    async def _fast_health(master: MasterClient) -> web.Response:
        """Fast-path: return cluster health without LLM."""
        tid = generate_trace_id()
        metrics.requests_total += 1
        try:
            workers = await master.list_workers()
            num_workers = len(workers)
            metrics.requests_success += 1
            return web.json_response({
                "trace_id": tid,
                "status": "completed",
                "conclusion": f"Cluster is healthy. {num_workers} worker(s) connected.",
                "fast_path": True,
                "data": {"workers_count": num_workers, "workers": workers},
            })
        except Exception as e:
            metrics.requests_failed += 1
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
                lines.append(f"  {wid}  [{load}]")
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

    async def _fast_tool(master: MasterClient, intent: RouterResult) -> web.Response:
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
                data = result.get("data", {})
                if isinstance(data, dict) and data:
                    # Build a concise natural-language summary from tool output.
                    parts = []
                    if intent.tool_name == "system.info":
                        host = data.get("hostname", "")
                        os_name = data.get("os", "")
                        arch = data.get("arch", "")
                        uptime = data.get("uptime_seconds", 0)
                        cores = data.get("cpu_cores", "")
                        host_part = f"节点{host}" if host else ""
                        os_part = f"运行{os_name}" if os_name else ""
                        arch_part = f"({arch})" if arch else ""
                        parts.append(f"{host_part} {os_part}{arch_part}".strip())
                        if uptime:
                            parts.append(f"已运行{_fmt_duration(uptime)}")
                        if cores:
                            parts.append(f"{cores}核CPU")
                        conclusion = "，".join(parts) if parts else f"已执行 {intent.tool_name}"
                    elif intent.tool_name == "cpu.usage":
                        load_1 = data.get("load_1min", "")
                        load_5 = data.get("load_5min", "")
                        cores = data.get("cpu_cores", "")
                        parts.append(f"CPU负载: 1min={load_1} 5min={load_5}")
                        if cores:
                            parts.append(f"{cores}核")
                        conclusion = " | ".join(parts)
                    elif intent.tool_name == "memory.usage":
                        total = data.get("total_gb", "")
                        free = data.get("free_gb", "")
                        avail = data.get("available_gb", "")
                        conclusion = f"内存: 总计{total}GB 可用{avail}GB 空闲{free}GB"
                    elif intent.tool_name == "disk.usage":
                        total = data.get("total_bytes", 0)
                        used = data.get("used_bytes", 0)
                        pct = data.get("usage_pct", "")
                        conclusion = f"磁盘: 总计{_fmt_bytes(total)} 已用{_fmt_bytes(used)} ({pct})"
                    elif intent.tool_name == "file.list":
                        path = data.get("path", "")
                        files = data.get("files", [])
                        if isinstance(files, list):
                            conclusion = f"目录{path}: {len(files)}个项目"
                        else:
                            conclusion = f"已执行 {intent.tool_name}"
                    elif intent.tool_name == "container.list":
                        containers = data if isinstance(data, list) else data.get("containers", [])
                        if isinstance(containers, list):
                            running = sum(1 for c in containers if c.get("status") == "running")
                            conclusion = f"容器: {len(containers)}个 (运行{running})"
                        else:
                            conclusion = f"已执行 {intent.tool_name}"
                    else:
                        summary = "; ".join(f"{k}={v}" for k, v in list(data.items())[:5])
                        if summary:
                            conclusion = f"{intent.tool_name}: {summary}"
                        else:
                            conclusion = f"已执行 {intent.tool_name}"
                else:
                    conclusion = f"已执行 {intent.tool_name}"
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
        metrics.requests_total += 1

        # Authentication check.
        token = _extract_bearer(request)
        if not _authenticate(token, cfg.cluster_token):
            metrics.requests_failed += 1
            return web.json_response(
                {"error": "AUTH_FAILED", "message": "Invalid or missing token"},
                status=401,
            )

        # Rate limit check.
        client_ip = request.remote or "unknown"
        if not rate_limiter.allow(client_ip):
            metrics.requests_failed += 1
            logger.warning("Rate limit exceeded", extra={"data": {"client_ip": client_ip}})
            return web.json_response(
                {"error": "RATE_LIMITED", "message": "Too many requests. Try again later."},
                status=429,
            )

        global engine, router
        if not engine:
            metrics.requests_failed += 1
            return web.json_response({"error": "Brain not initialized"}, status=503)

        try:
            body = await request.json()
        except Exception:
            metrics.requests_failed += 1
            return web.json_response({"error": "invalid JSON"}, status=400)

        message = (body.get("message") or "").strip()
        if not message:
            metrics.requests_failed += 1
            return web.json_response({"error": "message is required"}, status=400)

        logger.info("Chat request", extra={"data": {"message": message[:100]}})

        # ── Fast-path: LLM-based intent routing ───────────────────────
        result = await router.route(message)

        if result.category == RouterCategory.IRRELEVANT:
            metrics.requests_success += 1
            return web.json_response({
                "trace_id": generate_trace_id(),
                "status": "rejected",
                "conclusion": result.reason or "Message rejected.",
                "fast_path": True,
            })

        if result.category == RouterCategory.GREETING:
            metrics.requests_success += 1
            return web.json_response({
                "trace_id": generate_trace_id(),
                "status": "completed",
                "conclusion": result.reason,
                "fast_path": True,
            })

        if result.category == RouterCategory.TOOL:
            if result.tool_name == "_health_check":
                return await _fast_health(master)
            if result.tool_name == "_list_workers":
                return await _fast_workers(master)
            return await _fast_tool(master, result)

        # result.category == TROUBLESHOOT → proceed to LLM pipeline.
        trace_id = await engine.start_session(message)

        # Wait for completion with timeout.
        task = engine.active_sessions.get(trace_id)
        if task:
            try:
                await asyncio.wait_for(task, timeout=180.0)
            except asyncio.TimeoutError:
                metrics.requests_success += 1
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
        status_str = result.get("status", "")
        if status_str in ("completed", "success"):
            metrics.requests_success += 1
        else:
            metrics.requests_failed += 1
        return web.json_response(result)

    health_app.router.add_get("/health", health_handler)
    health_app.router.add_get("/metrics", metrics_handler)
    health_app.router.add_post("/api/chat", chat_handler)
    global health_runner
    health_runner = web.AppRunner(health_app)
    await health_runner.setup()
    health_site = web.TCPSite(health_runner, "0.0.0.0", 9091)
    await health_site.start()
    logger.info("Health endpoint listening", extra={"data": {"addr": "0.0.0.0:9091"}})

    # Keep alive indefinitely.
    await asyncio.Event().wait()


async def _do_shutdown() -> None:
    """Async shutdown — drain sessions, then HTTP server."""
    global health_runner
    if engine:
        for _, task in list(engine.active_sessions.items()):
            task.cancel()
    if health_runner:
        try:
            await asyncio.wait_for(health_runner.cleanup(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
    asyncio.get_event_loop().stop()


def _shutdown(sig: signal.Signals) -> None:
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    logger.info("Brain shutting down", extra={"data": {"signal": sig.name}})
    asyncio.create_task(_do_shutdown())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT)
