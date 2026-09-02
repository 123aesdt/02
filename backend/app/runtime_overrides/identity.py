import hashlib
import json

from app.runtime_overrides.models import RuntimeOverrideCommand


def payload_fingerprint(command: RuntimeOverrideCommand) -> str:
    payload = json.dumps(
        command.to_fingerprint_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
