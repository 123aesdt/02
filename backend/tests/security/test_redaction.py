import json
import logging

from pydantic import SecretStr

from app.observability.logging import SafeJsonFormatter
from app.security.redaction import SensitiveDataRedactor


def test_security_log_redaction() -> None:
    redactor = SensitiveDataRedactor()
    source = {
        "Authorization": "Bearer header.payload.signature",
        "nested": [{"api-key": "secret-api-value", "safe": "visible"}],
        "password": SecretStr("secret-password"),
        "url": "https://user:secret-password@example.test/path",
    }

    result = redactor.redact(source)
    serialized = json.dumps(result)

    assert result["Authorization"] == "[REDACTED]"
    assert result["nested"][0]["api-key"] == "[REDACTED]"
    assert result["nested"][0]["safe"] == "visible"
    for forbidden in ("header.payload.signature", "secret-api-value", "secret-password"):
        assert forbidden not in serialized


def test_ws_ticket_not_logged() -> None:
    formatter = SafeJsonFormatter(service="backend", runtime_profile="test")
    ticket = "A" * 43
    record = logging.LogRecord(
        "countyflow",
        logging.INFO,
        __file__,
        1,
        f"websocket /api/v1/ws/tasks/TASK-1?ticket={ticket}&last_event_id=1-0",
        (),
        None,
    )

    rendered = formatter.format(record)

    assert ticket not in rendered
    assert "ticket=[REDACTED]" in rendered


def test_error_response_no_secret() -> None:
    redactor = SensitiveDataRedactor()
    rendered = redactor.redact("Bearer header.payload.signature failed at redis://user:password@redis:6379/0")

    assert "header.payload.signature" not in rendered
    assert "password" not in rendered
