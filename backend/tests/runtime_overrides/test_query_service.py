from dataclasses import replace

import pytest

from app.runtime_overrides.query_models import RuntimeInterventionEligibility
from app.runtime_overrides.query_service import RuntimeOverrideQueryError, RuntimeOverrideQueryService
from app.runtime_threads.checkpoint_store import RuntimeCheckpointStoreError
from app.runtime_threads.models import CheckpointRecord, RuntimeThreadStatus
from app.security.permissions import Role
from tests.security_support import principal_for

from .factories import NOW, normal_state, stable_environment_thread


class ThreadRepository:
    def __init__(self, thread=None) -> None:
        self.thread = thread or stable_environment_thread()

    def get_by_thread_id(self, thread_id: str):
        return self.thread if thread_id == self.thread.thread_id else None


class CheckpointStore:
    def __init__(self, state=None, *, error: bool = False) -> None:
        self.state = normal_state() if state is None else state
        self.error = error
        self.requested: list[tuple[str, str]] = []

    async def get_exact(self, thread_id: str, checkpoint_id: str):
        self.requested.append((thread_id, checkpoint_id))
        if self.error:
            raise RuntimeCheckpointStoreError
        if self.state is None:
            return None
        return CheckpointRecord(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id="checkpoint-c6",
            checkpoint_namespace="",
            state=self.state,
            metadata={},
            config={"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}},
            serialized_size_bytes=1024,
        )


def service(*, thread=None, state=None, store=None):
    return RuntimeOverrideQueryService(
        override_repository=None,
        thread_repository=ThreadRepository(thread),
        checkpoint_store=store or CheckpointStore(state),
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_intervention_context_eligible() -> None:
    result = await service().get_intervention_context(
        stable_environment_thread().thread_id, principal_for(Role.SUPERVISOR)
    )

    assert result.eligibility is RuntimeInterventionEligibility.ELIGIBLE
    assert result.can_override is True
    assert result.canonical_checkpoint_id == "checkpoint-c7"
    assert result.target is not None
    assert (result.target.entity_type, result.target.entity_id, result.target.field) == (
        "Vehicle",
        "vehicle-001",
        "status",
    )
    assert result.target.allowed_new_values == ("BROKEN", "UNAVAILABLE", "MAINTENANCE")


@pytest.mark.asyncio
async def test_intervention_context_not_stable() -> None:
    thread = replace(stable_environment_thread(), status=RuntimeThreadStatus.RUNNING)
    result = await service(thread=thread).get_intervention_context(thread.thread_id, principal_for(Role.SUPERVISOR))

    assert (result.eligibility, result.eligibility_reason_code) == (
        RuntimeInterventionEligibility.NOT_STABLE,
        "THREAD_NOT_STABLE",
    )


@pytest.mark.asyncio
async def test_intervention_context_terminal() -> None:
    thread = replace(stable_environment_thread(), status=RuntimeThreadStatus.TERMINAL, next_node=None)
    result = await service(thread=thread).get_intervention_context(thread.thread_id, principal_for(Role.SUPERVISOR))

    assert (result.eligibility, result.eligibility_reason_code) == (
        RuntimeInterventionEligibility.TERMINAL,
        "THREAD_TERMINAL",
    )


@pytest.mark.asyncio
async def test_intervention_context_no_permission() -> None:
    result = await service().get_intervention_context(stable_environment_thread().thread_id, principal_for(Role.OPERATOR))

    assert (result.eligibility, result.can_override) == (
        RuntimeInterventionEligibility.NO_PERMISSION,
        False,
    )


@pytest.mark.asyncio
async def test_intervention_context_wrong_boundary() -> None:
    thread = replace(stable_environment_thread(), current_node="capacity", next_node="routing")
    result = await service(thread=thread).get_intervention_context(thread.thread_id, principal_for(Role.SUPERVISOR))

    assert (result.eligibility, result.eligibility_reason_code) == (
        RuntimeInterventionEligibility.WRONG_BOUNDARY,
        "RUNTIME_OVERRIDE_WRONG_BOUNDARY",
    )


@pytest.mark.asyncio
async def test_intervention_context_busy() -> None:
    thread = replace(stable_environment_thread(), status=RuntimeThreadStatus.OVERRIDING)
    result = await service(thread=thread).get_intervention_context(thread.thread_id, principal_for(Role.SUPERVISOR))

    assert (result.eligibility, result.eligibility_reason_code) == (
        RuntimeInterventionEligibility.BUSY,
        "RUNTIME_OVERRIDE_BUSY",
    )


@pytest.mark.asyncio
async def test_intervention_context_uses_exact_canonical_checkpoint() -> None:
    store = CheckpointStore()
    thread = stable_environment_thread()

    await service(thread=thread, store=store).get_intervention_context(
        thread.thread_id, principal_for(Role.SUPERVISOR)
    )

    assert store.requested == [(thread.thread_id, "checkpoint-c7")]


@pytest.mark.asyncio
async def test_intervention_context_fails_closed_when_checkpoint_store_is_unavailable() -> None:
    with pytest.raises(RuntimeOverrideQueryError) as captured:
        await service(store=CheckpointStore(error=True)).get_intervention_context(
            stable_environment_thread().thread_id, principal_for(Role.SUPERVISOR)
        )

    assert captured.value.code == "CHECKPOINT_STORE_UNAVAILABLE"
