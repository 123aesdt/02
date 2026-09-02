from dataclasses import replace

from app.observability.context import bind_observability_context, current_correlation_id, normalize_correlation_id
from app.streams.models import DispatchTaskMessage
from tests.workers.test_dispatch_worker import _task


def test_correlation_id_is_bounded_and_context_resets() -> None:
    generated = normalize_correlation_id("invalid value with spaces")
    assert len(generated) == 32
    assert generated.isalnum()

    with bind_observability_context(correlation_id="ops-123"):
        assert current_correlation_id() == "ops-123"
    assert current_correlation_id() is None


def test_dispatch_message_correlation_is_backward_compatible() -> None:
    original = _task()
    correlated = replace(original, correlation_id="ops-123")

    restored = DispatchTaskMessage.from_json(correlated.to_json())
    legacy = DispatchTaskMessage.from_json(original.to_json())

    assert restored.correlation_id == "ops-123"
    assert legacy.correlation_id is None
