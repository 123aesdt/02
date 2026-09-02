import hashlib
import json
from enum import Enum

from app.shared_memory.models import SharedMemoryMutationCommand


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_fact_key(command: SharedMemoryMutationCommand) -> str:
    return f"smf_{_digest(command.fact_identity())}"


def content_fingerprint(command: SharedMemoryMutationCommand) -> str:
    return _digest(
        {
            "subject_type": command.subject_type,
            "subject_id": command.subject_id,
            "predicate": command.predicate,
            "object_type": command.object_type,
            "object_id": command.object_id,
            "value_json": command.value_json,
        }
    )


def payload_fingerprint(command: SharedMemoryMutationCommand) -> str:
    payload = command.to_dict()
    payload.pop("idempotency_key")
    return _digest(payload)


def evidence_fingerprint(command: SharedMemoryMutationCommand) -> str:
    return _digest(
        {
            "source_type": command.source_type,
            "source_id": command.source_id,
            "evidence_text": command.evidence_text,
            "evidence_ref": command.evidence_ref,
            "observed_at": (
                command.evidence_observed_at.isoformat() if command.evidence_observed_at else None
            ),
            "confidence": format(command.confidence, "f"),
        }
    )

