from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission

router = APIRouter(prefix="/api/v1/security/audit", tags=["security-audit"])


def get_repository(request: Request):
    return request.app.state.security_audit_repository


RepositoryDependency = Annotated[object, Depends(get_repository)]
AuditReadPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.AUDIT_READ))]


@router.get("")
def list_security_audit(
    repository: RepositoryDependency,
    _principal: AuditReadPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, object]:
    return {
        "items": [
            {
                **event.to_record(),
                "created_at": event.created_at.isoformat(),
            }
            for event in repository.list_recent(limit=limit)
        ]
    }
