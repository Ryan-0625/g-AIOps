"""Dynamic tool deployer — deploys missing tools to Workers via tool.create.

When a tool execution fails with NO_AVAILABLE_WORKER and the tool has a
predefined script template, the deployer creates a script-based tool on
the Worker and retries the execution.

Deployed tools persist on the Worker (under the dynamic tools directory)
so they are available for future sessions without re-deployment.
"""

from typing import Any

from logger.structured_logger import get_logger

logger = get_logger()

# ── Predefined script templates (readonly, safe) ─────────────────────
# Scripts must output valid JSON to stdout.
# Uses printf with %s format strings to avoid JSON quoting issues.
# Keep awk usage minimal — only in memory.usage where /proc/meminfo
# values need division.

TEMPLATES: dict[str, dict[str, str]] = {
    "system.info": {
        "script": (
            'printf \'{"hostname":"%s","os":"%s","arch":"%s",'
            '"uptime_seconds":%s,"cpu_cores":%s}\\n\' '
            '"$(hostname 2>/dev/null)" '
            '"$(uname -s 2>/dev/null)" '
            '"$(uname -m 2>/dev/null)" '
            '"$(head -1 /proc/uptime 2>/dev/null | cut -d. -f1 || echo 0)" '
            '"$(nproc 2>/dev/null || echo 1)"'
        ),
        "interpreter": "bash",
        "description": "Get system information (OS, kernel, hostname, uptime, CPU, memory)",
    },
    "cpu.usage": {
        "script": (
            'LOAD=$(cat /proc/loadavg 2>/dev/null || echo "0 0 0")\n'
            'set -- $LOAD\n'
            'CORES=$(nproc 2>/dev/null || echo 1)\n'
            'printf \'{"cpu_cores":%s,"load_1min":%s,"load_5min":%s,"load_15min":%s}\\n\' '
            '"$CORES" "$1" "$2" "$3"'
        ),
        "interpreter": "bash",
        "description": "Get CPU usage, load average, and core count",
    },
    "memory.usage": {
        "script": (
            'printf \'{"total_gb":%s,"free_gb":%s,"available_gb":%s}\\n\' '
            '"$(grep MemTotal /proc/meminfo 2>/dev/null '
            '| awk \'{printf "%.2f", $2/1024/1024}\' || echo 0)" '
            '"$(grep MemFree /proc/meminfo 2>/dev/null '
            '| awk \'{printf "%.2f", $2/1024/1024}\' || echo 0)" '
            '"$(grep MemAvailable /proc/meminfo 2>/dev/null '
            '| awk \'{printf "%.2f", $2/1024/1024}\' || echo 0)"'
        ),
        "interpreter": "bash",
        "description": "Get memory usage (total, free, available)",
    },
    "disk.usage": {
        "script": (
            'printf \'{"path":"%s","total_bytes":%s,"used_bytes":%s,'
            '"available_bytes":%s,"usage_pct":"%s"}\\n\' '
            '"/" '
            '"$(df -B1 / 2>/dev/null | tail -1 | awk \'{print $2}\' || echo 0)" '
            '"$(df -B1 / 2>/dev/null | tail -1 | awk \'{print $3}\' || echo 0)" '
            '"$(df -B1 / 2>/dev/null | tail -1 | awk \'{print $4}\' || echo 0)" '
            '"$(df -h / 2>/dev/null | tail -1 | awk \'{print $5}\' || echo 0%)"'
        ),
        "interpreter": "bash",
        "description": "Check disk usage of root mount point",
    },
    "network.connections": {
        "script": (
            'echo \'{"connections":[\'\n'
            'ss -tuna 2>/dev/null | tail -n +2 | head -20 '
            '| while read line; do\n'
            '  set -- $line\n'
            '  echo \'{"proto":"\'"$1"\'","local":"\'"$5"\'","remote":"\'"$6"\'","state":"\'"$2"\'"},\'\n'
            'done\n'
            'echo \']}\''
        ),
        "interpreter": "bash",
        "description": "List active network connections (top 20)",
    },
}


class Deployer:
    """Deploys missing tools to Workers dynamically.

    Uses predefined script templates (safer than LLM-generated scripts).
    Deploys via tool.create. Tools persist on Worker for future sessions.
    """

    def __init__(self, master):
        self._master = master
        self._deployed: set[str] = set()

    def has_template(self, action: str) -> bool:
        """Check if a deployable template exists for this action."""
        return action in TEMPLATES

    async def deploy(self, action: str, trace_id: str, target_worker: str | None = None) -> bool:
        """Deploy a tool to a Worker. Returns True on success."""
        tmpl = TEMPLATES.get(action)
        if not tmpl:
            logger.warning("No deploy template", extra={"data": {"action": action}})
            return False

        logger.info("Deploying tool", extra={
            "data": {"action": action, "target_worker": target_worker or "any"},
        })

        try:
            params: dict[str, Any] = {
                "name": action,
                "script": tmpl["script"],
                "interpreter": tmpl["interpreter"],
                "description": tmpl.get("description", f"Dynamic {action} tool"),
                "risk_level": "readonly",
                "timeout": 30,
            }
            if target_worker:
                params["target_worker_id"] = target_worker

            result = await self._master.execute(
                action="tool.create",
                params=params,
                trace_id=trace_id,
            )

            if result.get("status") == "success":
                self._deployed.add(action)
                logger.info("Tool deployed", extra={"data": {"action": action}})
                return True

            logger.warning("Deploy failed", extra={
                "data": {"action": action, "error": result.get("error", {})},
            })
            return False

        except Exception as e:
            logger.error("Deploy error", extra={
                "data": {"action": action, "error": str(e)},
            })
            return False

    async def undeploy(self, action: str, trace_id: str) -> bool:
        """Remove a previously deployed tool. Returns True on success."""
        if action not in self._deployed:
            return True

        try:
            result = await self._master.execute(
                action="tool.delete",
                params={"name": action},
                trace_id=trace_id,
            )
            self._deployed.discard(action)
            logger.info("Tool undeployed", extra={"data": {"action": action}})
            return result.get("status") == "success"
        except Exception as e:
            logger.warning("Undeploy error", extra={
                "data": {"action": action, "error": str(e)},
            })
            return False

    async def cleanup_all(self, trace_id: str) -> None:
        """Remove all deployed tools."""
        for action in list(self._deployed):
            await self.undeploy(action, trace_id)
