"""Trace context — per-coroutine trace_id/msg_id via contextvars."""

import uuid
from contextvars import ContextVar

current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
current_msg_id: ContextVar[str] = ContextVar("msg_id", default="")


def set_trace_id(trace_id: str) -> None:
    current_trace_id.set(trace_id)


def get_trace_id() -> str:
    return current_trace_id.get()


def set_msg_id(msg_id: str) -> None:
    current_msg_id.set(msg_id)


def get_msg_id() -> str:
    return current_msg_id.get()


def generate_trace_id() -> str:
    return str(uuid.uuid4())


def generate_msg_id() -> str:
    return str(uuid.uuid4())
