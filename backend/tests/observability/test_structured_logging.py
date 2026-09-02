import json
import logging

from pydantic import SecretStr

from app.observability.logging import SafeJsonFormatter, configure_structured_logging


def test_json_log_never_serializes_secrets() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "provider failed", (), None)
    record.api_key = SecretStr("forbidden-value")
    record.authorization = "Bearer also-forbidden"
    record.error_code = "PROVIDER_UNAVAILABLE"

    payload = SafeJsonFormatter(service="countyflow-test", runtime_profile="test").format(record)

    assert "forbidden-value" not in payload
    assert "also-forbidden" not in payload
    assert json.loads(payload)["error_code"] == "PROVIDER_UNAVAILABLE"


def test_structured_logging_configures_existing_handlers() -> None:
    logger = logging.Logger("countyflow-test")
    handler = logging.StreamHandler()
    logger.addHandler(handler)

    configure_structured_logging("backend", "docker-dev", logger=logger)

    assert isinstance(handler.formatter, SafeJsonFormatter)
