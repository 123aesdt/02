import re
from urllib.parse import urlsplit

_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(api[_-]?key|password|token)\s*[=:]\s*[^\s,;]+"),
)


def sanitize_audit_text(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = value
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def validate_safe_reference(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("evidence_ref must not contain credentials")
    return value

