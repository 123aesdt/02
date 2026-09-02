from app.runtime_overrides.identity import payload_fingerprint

from .test_models import command


def test_runtime_override_idempotent_replay() -> None:
    assert payload_fingerprint(command()) == payload_fingerprint(command())
    assert len(payload_fingerprint(command())) == 64


def test_runtime_override_idempotency_payload_conflict() -> None:
    assert payload_fingerprint(command(new_value="BROKEN")) != payload_fingerprint(
        command(new_value="MAINTENANCE")
    )
