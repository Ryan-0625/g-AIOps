"""Tool calling schemas — maps action definitions to LLM function calling format."""

from typing import Any


def tool_to_ollama_schema(tool_name: str, description: str, params: dict[str, Any]) -> dict[str, Any]:
    """Convert a tool definition to Ollama function calling format."""
    # Append optional target_worker_id to every tool schema.
    worker_param: dict[str, Any] = {
        "target_worker_id": {
            "type": "string",
            "description": "Target worker ID (e.g. worker-1). If not specified, Master routes to least-loaded worker.",
            "required": False,
        },
    }
    all_params = {**worker_param, **params}
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": all_params,
                "required": [k for k, v in all_params.items() if v.get("required")],
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

HTTP_GET = tool_to_ollama_schema(
    "http.get",
    "Perform an HTTP GET request to fetch a URL.",
    {
        "url": {"type": "string", "description": "Target URL (http/https)", "required": True},
        "headers": {"type": "string", "description": "Optional HTTP headers as JSON object"},
        "timeout_seconds": {"type": "integer", "description": "Request timeout in seconds (1-60)"},
    },
)

HTTP_POST = tool_to_ollama_schema(
    "http.post",
    "Perform an HTTP POST request with a body payload.",
    {
        "url": {"type": "string", "description": "Target URL (http/https)", "required": True},
        "body": {"type": "string", "description": "Request body content"},
        "content_type": {"type": "string", "description": "Content-Type header (default application/json)"},
        "headers": {"type": "string", "description": "Optional HTTP headers as JSON object"},
        "timeout_seconds": {"type": "integer", "description": "Request timeout in seconds (1-60)"},
    },
)

DNS_LOOKUP = tool_to_ollama_schema(
    "dns.lookup",
    "Resolve DNS records for a hostname.",
    {
        "hostname": {"type": "string", "description": "Hostname to resolve", "required": True},
        "record_type": {"type": "string", "description": "Record type: A, AAAA, MX, TXT, CNAME (default A)"},
    },
)

SYSTEM_INFO = tool_to_ollama_schema(
    "system.info",
    "Get system information including OS, kernel, hostname, uptime, CPU, and memory.",
    {},
)

FILE_READ = tool_to_ollama_schema(
    "file.read",
    "Read a file from the filesystem. Sensitive paths are blocked.",
    {
        "path": {"type": "string", "description": "File path to read", "required": True},
        "max_bytes": {"type": "integer", "description": "Maximum bytes to read (default 4096, max 65536)"},
    },
)

FILE_WRITE = tool_to_ollama_schema(
    "file.write",
    "Write content to a file. Only allowed in /tmp/ and /var/tmp/. Requires approval.",
    {
        "path": {"type": "string", "description": "File path to write", "required": True},
        "content": {"type": "string", "description": "Content to write", "required": True},
        "mode": {"type": "string", "description": "File mode (e.g. 644)"},
        "append": {"type": "boolean", "description": "Append instead of overwrite"},
    },
)

NETWORK_CONNECTIONS = tool_to_ollama_schema(
    "network.connections",
    "List active network connections from /proc/net.",
    {
        "protocol": {"type": "string", "description": "Protocol: tcp, udp, all (default tcp)"},
        "state": {"type": "string", "description": "State: established, listening, all (default all)"},
    },
)

CONTAINER_LIST = tool_to_ollama_schema(
    "container.list",
    "List Docker containers via the Docker socket.",
    {
        "all": {"type": "boolean", "description": "Show all containers including stopped (default false)"},
    },
)

TOOL_CREATE = tool_to_ollama_schema(
    "tool.create",
    "Create a temporary tool on a Worker. Use when no Worker supports a needed action.",
    {
        "name": {"type": "string", "description": "Tool name (e.g. custom.deploy)", "required": True},
        "description": {"type": "string", "description": "Human-readable description of the tool"},
        "script": {"type": "string", "description": "Script content to execute", "required": True},
        "interpreter": {"type": "string", "description": "Script interpreter: bash, python3, or node (default bash)"},
        "params_schema": {"type": "string", "description": "JSON schema describing tool parameters"},
        "timeout": {"type": "integer", "description": "Execution timeout in seconds (max 300)"},
        "risk_level": {"type": "string", "description": "Risk level: readonly, write, dangerous (default dangerous)"},
    },
)

TOOL_DELETE = tool_to_ollama_schema(
    "tool.delete",
    "Delete a previously created temporary tool.",
    {
        "name": {"type": "string", "description": "Tool name to delete", "required": True},
    },
)

ALL_TOOLS = [PING_ICMP, DISK_USAGE, SERVICE_STATUS, SERVICE_RESTART,
             HTTP_GET, HTTP_POST, DNS_LOOKUP, SYSTEM_INFO,
             FILE_READ, FILE_WRITE, NETWORK_CONNECTIONS, CONTAINER_LIST,
             TOOL_CREATE, TOOL_DELETE]
TOOL_NAMES = [t["function"]["name"] for t in ALL_TOOLS]
