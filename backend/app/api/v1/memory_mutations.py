from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.v1.memory_schemas import CreateMemoryMutationRequest, MemoryMutationResponse
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.security.rate_limit import OperationClass, RateLimitDecision, require_rate_limit
from app.shared_memory.policy import MemoryVersionConflict
from app.shared_memory.service import (
    MemoryMutationBusy,
    MemoryMutationValidationError,
    SharedMemoryMutationService,
)
from app.shared_memory.sqlalchemy_repository import MemoryIdempotencyConflict

router = APIRouter(prefix="/api/v1/memory", tags=["memory-management"])


def get_service(request: Request) -> SharedMemoryMutationService:
    return request.app.state.shared_memory_service


ServiceDependency = Annotated[SharedMemoryMutationService, Depends(get_service)]
MemoryMutatePrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.MEMORY_MUTATE))]
MemoryReadPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.MEMORY_READ))]
MemoryMutationRateLimit = Annotated[
    RateLimitDecision,
    Depends(require_rate_limit(OperationClass.MEMORY_MUTATION)),
]


@router.post("/mutations", response_model=MemoryMutationResponse)
async def create_memory_mutation(
    payload: CreateMemoryMutationRequest,
    service: ServiceDependency,
    principal: MemoryMutatePrincipal,
    _rate_limit: MemoryMutationRateLimit,
) -> MemoryMutationResponse | JSONResponse:
    try:
        result = await service.mutate(payload.to_command(operator_id=principal.subject_id))
    except MemoryVersionConflict as error:
        return JSONResponse(
            status_code=409,
            content={
                "code": "MEMORY_VERSION_CONFLICT",
                "message": str(error),
                "details": {
                    "fact_key": error.fact_key,
                    "expected_version": error.expected_version,
                    "actual_version": error.actual_version,
                },
            },
        )
    except MemoryIdempotencyConflict as error:
        return JSONResponse(
            status_code=409,
            content={"code": "MEMORY_IDEMPOTENCY_CONFLICT", "message": str(error)},
        )
    except MemoryMutationBusy as error:
        return JSONResponse(
            status_code=409,
            content={
                "code": "MEMORY_MUTATION_BUSY",
                "message": str(error),
                "details": {"fact_key": error.fact_key},
            },
        )
    except MemoryMutationValidationError as error:
        return JSONResponse(
            status_code=422,
            content={"code": "MEMORY_MUTATION_INVALID", "message": str(error)},
        )
    response = MemoryMutationResponse.model_validate(result.to_dict())
    if result.projection_incomplete:
        return JSONResponse(status_code=202, content=response.model_dump(mode="json"))
    return response


@router.get("/mutations/{mutation_id}", response_model=MemoryMutationResponse)
def get_memory_mutation(
    mutation_id: str,
    service: ServiceDependency,
    _principal: MemoryReadPrincipal,
) -> MemoryMutationResponse:
    try:
        return MemoryMutationResponse.model_validate(
            service.get_mutation_result(mutation_id).to_dict()
        )
    except LookupError as error:
        raise HTTPException(404, detail={"code": "MEMORY_MUTATION_NOT_FOUND"}) from error


@router.get("/facts/{fact_key}")
def get_memory_fact(fact_key: str, service: ServiceDependency, principal: MemoryReadPrincipal) -> dict[str, object]:
    try:
        detail = service.get_fact_detail(fact_key)
    except LookupError as error:
        raise HTTPException(404, detail={"code": "MEMORY_FACT_NOT_FOUND"}) from error
    if principal.can(Permission.AUDIT_READ):
        return detail
    projected = dict(detail)
    projected["evidence"] = []
    projected["mutations"] = [
        {
            key: value
            for key, value in mutation.items()
            if key not in {"operator_id", "source_type", "source_id"}
        }
        for mutation in detail.get("mutations", [])
        if isinstance(mutation, dict)
    ]
    return projected
