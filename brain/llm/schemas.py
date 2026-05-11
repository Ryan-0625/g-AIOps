"""Tool calling schemas — maps action definitions to LLM function calling format."""

from typing import Any


def tool_to_ollama_schema(tool_name: str, description: str, params: dict[str, Any]) -> dict[str, Any]:
    """Convert a tool definition to Ollama function calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": [k for k, v in params.items() if v.get("required")],
            },
        },
    }


# ── Built-in tool schemas ──────────────────────────────────────────────

PING_ICMP = tool_to_ollama_schema(
    "ping.icmp",
    "ICMP/TCP ping a target host to check reachability and latency.",
    {
        "target": {"type": "string", "description": "Hostname or IP address", "required": True},
        "count": {"type": "integer", "description": "Number of pings (1-10)", "required": False},
    },
)

DISK_USAGE = tool_to_ollama_schema(
    "disk.usage",
    "Check disk usage for a mount point.",
    {
        "path": {"type": "string", "description": "Mount point path (e.g. /, /data)", "required": False},
    },
)

SERVICE_STATUS = tool_to_ollama_schema(
    "service.status",
    "Check the status of a systemd service.",
    {
        "name": {"type": "string", "description": "Service name (e.g. nginx, sshd)", "required": True},
    },
)

SERVICE_RESTART = tool_to_ollama_schema(
    "service.restart",
    "Restart a systemd service. Requires human approval.",
    {
        "name": {"type": "string", "description": "Service name", "required": True},
    },
)

ALL_TOOLS = [PING_ICMP, DISK_USAGE, SERVICE_STATUS, SERVICE_RESTART]
TOOL_NAMES = [t["function"]["name"] for t in ALL_TOOLS]
