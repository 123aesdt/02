"""Credential-safe structured logging primitives."""

import json
import logging
from datetime import UTC, datetime

from app.observability.context import current_correlation_id
from app.security.redaction import SensitiveDataRedactor

_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__)
_REDACTOR = SensitiveDataRedactor()


def _safe_value(key: str, value: object) -> object:
    return _REDACTOR.redact(value, key=key)


class SafeJsonFormatter(logging.Formatter):
    def __init__(self, *, service: str, runtime_profile: str) -> None:
        super().__init__()
        self.service = service
        self.runtime_profile = runtime_profile

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "runtime_profile": self.runtime_profile,
            "correlation_id": current_correlation_id(),
            "message": _REDACTOR.redact(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and key not in {"message", "asctime"}:
                payload[key] = _safe_value(key, value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_structured_logging(
    service: str,
    runtime_profile: str,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Attach the credential-safe JSON formatter to a process logger."""
    targets = [logger] if logger is not None else [
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.error"),
        logging.getLogger("uvicorn.access"),
    ]
    formatter = SafeJsonFormatter(service=service, runtime_profile=runtime_profile)
    for target in targets:
        if target is None:
            continue
        if not target.handlers and logger is not None:
            target.addHandler(logging.StreamHandler())
        for handler in target.handlers:
            handler.setFormatter(formatter)
