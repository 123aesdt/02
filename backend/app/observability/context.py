"""Bounded correlation context shared by API, Worker, events, and logs."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_correlation_id: ContextVar[str | None] = ContextVar("countyflow_correlation_id", default=None)


def normalize_correlation_id(value: str | None) -> str:
    return value if value is not None and _CORRELATION_PATTERN.fullmatch(value) else uuid4().hex


def safe_correlation_id(value: object) -> str | None:
    return value if isinstance(value, str) and _CORRELATION_PATTERN.fullmatch(value) else None


def current_correlation_id() -> str | None:
    return _correlation_id.get()


@contextmanager
def bind_observability_context(*, correlation_id: str | None):
    token = _correlation_id.set(normalize_correlation_id(correlation_id))
    try:
        yield
    finally:
        _correlation_id.reset(token)
