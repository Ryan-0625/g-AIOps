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
}

AVAILABLE_ACTIONS = list(REGISTRY.keys())
