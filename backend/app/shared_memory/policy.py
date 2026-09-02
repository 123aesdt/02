from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.shared_memory.identity import build_fact_key, content_fingerprint, evidence_fingerprint
from app.shared_memory.models import (
    MemoryFactStatus,
    MutationDecision,
    SharedMemoryMutationCommand,
)


class MemoryVersionConflict(Exception):
    def __init__(
        self,
        fact_key: str,
        expected_version: int | None,
        actual_version: int | None,
    ) -> None:
        super().__init__("Shared memory version does not match the canonical fact")
        self.fact_key = fact_key
        self.expected_version = expected_version
        self.actual_version = actual_version


@dataclass(frozen=True)
class MemoryPolicySettings:
    auto_apply_min_confidence: Decimal
    lower_confidence_reject_delta: Decimal

    def __post_init__(self) -> None:
        for name in ("auto_apply_min_confidence", "lower_confidence_reject_delta"):
            value = Decimal(str(getattr(self, name)))
            if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
                raise ValueError(f"{name} must be between 0 and 1")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class SharedMemoryFactSnapshot:
    fact_key: str
    version: int
    content_fingerprint: str
    confidence: Decimal
    status: MemoryFactStatus
    updated_at: datetime
    expires_at: datetime | None
    evidence_fingerprints: frozenset[str] = frozenset()

    def is_expired(self, now: datetime) -> bool:
        return self.status is MemoryFactStatus.EXPIRED or (
            self.expires_at is not None and self.expires_at <= now
        )


@dataclass(frozen=True)
class MemoryDecision:
    decision: MutationDecision
    reason_code: str
    before_version: int | None
    after_version: int | None
    proposed_status: MemoryFactStatus
    requires_projection: bool


def _decision(
    decision: MutationDecision,
    reason_code: str,
    current: SharedMemoryFactSnapshot | None,
    *,
    status: MemoryFactStatus,
    increments: bool,
    requires_projection: bool,
) -> MemoryDecision:
    before_version = current.version if current else None
    if current is None:
        after_version = 1 if increments else None
    else:
        after_version = current.version + 1 if increments else current.version
    return MemoryDecision(
        decision=decision,
        reason_code=reason_code,
        before_version=before_version,
        after_version=after_version,
        proposed_status=status,
        requires_projection=requires_projection,
    )


def evaluate_mutation(
    current: SharedMemoryFactSnapshot | None,
    command: SharedMemoryMutationCommand,
    settings: MemoryPolicySettings,
    *,
    now: datetime,
) -> MemoryDecision:
    actual_version = current.version if current else None
    if command.expected_version != actual_version:
        raise MemoryVersionConflict(
            current.fact_key if current else build_fact_key(command),
            command.expected_version,
            actual_version,
        )

    if command.confidence < settings.auto_apply_min_confidence and not command.human_confirmed:
        return _decision(
            MutationDecision.CONFLICT_REVIEW,
            "LOW_CONFIDENCE_REVIEW",
            current,
            status=MemoryFactStatus.CONFLICT if current else MemoryFactStatus.PENDING_REVIEW,
            increments=False,
            requires_projection=False,
        )

    if current is None:
        return _decision(
            MutationDecision.CREATE,
            "NEW_FACT",
            None,
            status=MemoryFactStatus.ACTIVE,
            increments=True,
            requires_projection=True,
        )

    if current.is_expired(now):
        return _decision(
            MutationDecision.REPLACE,
            "EXPIRED_FACT",
            current,
            status=MemoryFactStatus.ACTIVE,
            increments=True,
            requires_projection=True,
        )

    if content_fingerprint(command) == current.content_fingerprint:
        duplicate_evidence = evidence_fingerprint(command) in current.evidence_fingerprints
        metadata_unchanged = (
            command.confidence == current.confidence and command.expires_at == current.expires_at
        )
        if duplicate_evidence and metadata_unchanged:
            return _decision(
                MutationDecision.NOOP,
                "DUPLICATE_FACT_AND_EVIDENCE",
                current,
                status=current.status,
                increments=False,
                requires_projection=False,
            )
        return _decision(
            MutationDecision.MERGE,
            "NEW_EVIDENCE_OR_METADATA",
            current,
            status=MemoryFactStatus.ACTIVE,
            increments=True,
            requires_projection=True,
        )

    if command.human_confirmed:
        return _decision(
            MutationDecision.REPLACE,
            "HUMAN_CONFIRMED",
            current,
            status=MemoryFactStatus.ACTIVE,
            increments=True,
            requires_projection=True,
        )

    if command.incoming_at < current.updated_at:
        return _decision(
            MutationDecision.REJECT,
            "STALE_EVIDENCE",
            current,
            status=current.status,
            increments=False,
            requires_projection=False,
        )

    if current.confidence - command.confidence >= settings.lower_confidence_reject_delta:
        return _decision(
            MutationDecision.REJECT,
            "LOWER_CONFIDENCE",
            current,
            status=current.status,
            increments=False,
            requires_projection=False,
        )

    return _decision(
        MutationDecision.CONFLICT_REVIEW,
        "CONTENT_CONFLICT_REVIEW",
        current,
        status=MemoryFactStatus.CONFLICT,
        increments=False,
        requires_projection=False,
    )
