"""Tool registry — maps action names to their parameter schemas.

This is the Brain-side view of available Worker tools. The actual execution
happens on the Worker; Brain only knows the schema for LLM function calling.
"""

from typing import Any

REGISTRY: dict[str, dict[str, Any]] = {
    "ping.icmp": {
        "description": "ICMP/TCP ping a target host",
        "required_params": ["target"],
        "risk_level": "readonly",
        "params": {
            "target": {"type": "string", "description": "Hostname or IP"},
            "count": {"type": "integer", "description": "Ping count (1-10)"},
        },
    },
    "disk.usage": {
        "description": "Check disk usage of a mount point",
        "required_params": [],
        "risk_level": "readonly",
        "params": {
            "path": {"type": "string", "description": "Mount path (default /)"},
        },
    },
    "service.status": {
        "description": "Check systemd service status",
        "required_params": ["name"],
        "risk_level": "readonly",
        "params": {
            "name": {"type": "string", "description": "Service name"},
        },
    },
    "service.restart": {
        "description": "Restart a systemd service",
        "required_params": ["name"],
        "risk_level": "write",
        "params": {
            "name": {"type": "string", "description": "Service name"},
        },
    },
    "http.get": {
        "description": "Perform an HTTP GET request to a URL",
        "required_params": ["url"],
        "risk_level": "readonly",
        "params": {
            "url": {"type": "string", "description": "Target URL (http/https)"},
            "headers": {"type": "dict", "description": "Optional HTTP headers"},
            "timeout_seconds": {"type": "integer", "description": "Request timeout (1-60)"},
        },
    },
    "http.post": {
        "description": "Perform an HTTP POST request to a URL",
        "required_params": ["url"],
        "risk_level": "write",
        "params": {
            "url": {"type": "string", "description": "Target URL (http/https)"},
            "body": {"type": "string", "description": "Request body"},
            "content_type": {"type": "string", "description": "Content-Type header (default application/json)"},
            "headers": {"type": "dict", "description": "Optional HTTP headers"},
            "timeout_seconds": {"type": "integer", "description": "Request timeout (1-60)"},
        },
    },
    "dns.lookup": {
        "description": "DNS record lookup",
        "required_params": ["hostname"],
        "risk_level": "readonly",
        "params": {
            "hostname": {"type": "string", "description": "Hostname to resolve"},
            "record_type": {"type": "string", "description": "Record type: A, AAAA, MX, TXT, CNAME (default A)"},
        },
    },
    "system.info": {
        "description": "Get system information (OS, kernel, memory, CPU, uptime)",
        "required_params": [],
        "risk_level": "readonly",
        "params": {},
    },
    "file.read": {
        "description": "Read a file from the filesystem",
        "required_params": ["path"],
        "risk_level": "readonly",
        "params": {
            "path": {"type": "string", "description": "File path to read"},
            "max_bytes": {"type": "integer", "description": "Maximum bytes to read (default 4096, max 65536)"},
        },
    },
    "file.write": {
        "description": "Write content to a file (dangerous, requires approval)",
        "required_params": ["path", "content"],
        "risk_level": "dangerous",
        "params": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
            "mode": {"type": "string", "description": "File mode (e.g. 644, 755)"},
            "append": {"type": "boolean", "description": "Append to file instead of overwriting"},
        },
    },
    "network.connections": {
        "description": "List network connections from /proc/net",
        "required_params": [],
        "risk_level": "readonly",
        "params": {
            "protocol": {"type": "string", "description": "Protocol filter: tcp, udp, all (default tcp)"},
            "state": {"type": "string", "description": "State filter: established, listening, all"},
        },
    },
    "container.list": {
        "description": "List Docker containers via Docker socket",
        "required_params": [],
        "risk_level": "readonly",
        "params": {
            "all": {"type": "boolean", "description": "Show all containers (including stopped)"},
        },
    },
    "tool.create": {
        "description": "Create a temporary tool on a Worker. Script receives params via TOOL_PARAMS env var and must output JSON to stdout.",
        "required_params": ["name", "script"],
        "risk_level": "dangerous",
        "params": {
            "name": {"type": "string", "description": "Tool name (e.g. custom.deploy)"},
            "description": {"type": "string", "description": "Tool description"},
            "script": {"type": "string", "description": "Script content"},
            "interpreter": {"type": "string", "description": "Script interpreter: bash, python3, node"},
            "params_schema": {"type": "string", "description": "JSON schema for tool params"},
            "timeout": {"type": "integer", "description": "Execution timeout in seconds"},
            "risk_level": {"type": "string", "description": "Risk level: readonly, write, dangerous"},
        },
    },
    "tool.delete": {
        "description": "Delete a previously created temporary tool.",
        "required_params": ["name"],
        "risk_level": "dangerous",
        "params": {
            "name": {"type": "string", "description": "Tool name to delete"},
        },
    },
}

AVAILABLE_ACTIONS = list(REGISTRY.keys())
