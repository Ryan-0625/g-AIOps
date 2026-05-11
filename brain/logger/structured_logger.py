"""JSON-structured logger. All modules use this; output goes to stdout."""

import json
import logging
import os
import time
from .trace_context import get_trace_id, get_msg_id


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": record.levelname.lower(),
            "module": "brain",
            "trace_id": get_trace_id() or "no-trace",
            "msg_id": get_msg_id() or "",
            "action": getattr(record, "action", ""),
            "message": record.getMessage(),
            "error_code": getattr(record, "error_code", None),
            "data": getattr(record, "data", {}),
            "duration_ms": getattr(record, "duration_ms", 0),
            "pid": os.getpid(),
        }
        # Remove None values.
        return json.dumps({k: v for k, v in entry.items() if v is not None})


_handler = logging.StreamHandler()
_handler.setFormatter(JSONFormatter())

_logger = logging.getLogger("brain")
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)
_logger.propagate = False


def get_logger() -> logging.Logger:
    return _logger
