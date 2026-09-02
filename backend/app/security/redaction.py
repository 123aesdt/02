import re
from collections.abc import Mapping

from pydantic import SecretStr

REDACTED = "[REDACTED]"
SENSITIVE_KEY_MARKERS = (
    "authorization",
    "cookie",
    "token",
    "apikey",
    "password",
    "secret",
    "clientsecret",
    "privatekey",
)
BEARER_OR_BASIC = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
JWT_VALUE = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
CREDENTIAL_URL = re.compile(r"(?P<scheme>https?|redis|mysql|neo4j\+s?|bolt)://[^\s/@:]+:[^\s/@]+@", re.IGNORECASE)
QUERY_SECRET = re.compile(
    r"(?P<key>(?:access_token|refresh_token|api[_-]?key|client_secret|token|ticket|password|secret))=[^&\s\"']+",
    re.IGNORECASE,
)


class SensitiveDataRedactor:
    def __init__(self, *, maximum_string_length: int = 2_048, maximum_depth: int = 8) -> None:
        if maximum_string_length <= 0 or maximum_depth <= 0:
            raise ValueError("redaction bounds must be positive")
        self._maximum_string_length = maximum_string_length
        self._maximum_depth = maximum_depth

    def redact(self, value: object, *, key: str | None = None, _depth: int = 0) -> object:
        try:
            if key is not None and self._sensitive_key(key):
                return REDACTED
            if isinstance(value, SecretStr):
                return REDACTED
            if _depth >= self._maximum_depth:
                return "[TRUNCATED]"
            if isinstance(value, Mapping):
                return {
                    str(item_key): self.redact(item_value, key=str(item_key), _depth=_depth + 1)
                    for item_key, item_value in value.items()
                }
            if isinstance(value, (list, tuple, set, frozenset)):
                return [self.redact(item, _depth=_depth + 1) for item in value]
            if isinstance(value, str):
                return self._redact_text(value)
            if isinstance(value, (int, float, bool)) or value is None:
                return value
            return self._redact_text(str(value))
        except Exception:
            return REDACTED

    def _redact_text(self, value: str) -> str:
        bounded = value[: self._maximum_string_length]
        bounded = BEARER_OR_BASIC.sub(lambda match: f"{match.group(1)} {REDACTED}", bounded)
        bounded = JWT_VALUE.sub(REDACTED, bounded)
        bounded = CREDENTIAL_URL.sub(lambda match: f"{match.group('scheme')}://{REDACTED}@", bounded)
        return QUERY_SECRET.sub(lambda match: f"{match.group('key')}={REDACTED}", bounded)

    @staticmethod
    def _sensitive_key(key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)
