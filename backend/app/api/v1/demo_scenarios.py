from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm.exc import StaleDataError

from app.demo_reset import (
    DemoScenarioForbidden,
    DemoScenarioNotFound,
    DemoScenarioResetService,
    DemoScenarioStateIncomplete,
)
from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission

router = APIRouter(prefix="/api/v1/demo-scenarios", tags=["demo-scenarios"])


class DemoScenarioResetResponse(BaseModel):
    scenario_id: str
    status: Literal["READY"]
    message: str


def get_service(request: Request) -> DemoScenarioResetService:
    return request.app.state.demo_scenario_reset_service


ResetService = Annotated[DemoScenarioResetService, Depends(get_service)]
ResetPrincipal = Annotated[
    AuthenticatedPrincipal,
    Depends(require_permission(Permission.ANOMALIES_REPORT)),
]


@router.post("/{scenario_id}/reset", response_model=DemoScenarioResetResponse)
def reset_demo_scenario(
    scenario_id: str,
    request: Request,
    service: ResetService,
    principal: ResetPrincipal,
) -> DemoScenarioResetResponse | JSONResponse:
    if request.app.state.runtime_profile != "docker-dev":
        return _error(404, "DEMO_SCENARIO_NOT_FOUND", "未找到演示场景。")
    try:
        result = service.reset(scenario_id, principal_subject_id=principal.subject_id)
    except DemoScenarioNotFound:
        return _error(404, "DEMO_SCENARIO_NOT_FOUND", "未找到演示场景。")
    except DemoScenarioForbidden:
        return _error(403, "DEMO_SCENARIO_FORBIDDEN", "当前演示身份不能复位该场景。")
    except DemoScenarioStateIncomplete:
        return _error(409, "DEMO_SCENARIO_STATE_INCOMPLETE", "演示基础数据不完整，未执行复位。")
    except StaleDataError:
        return _error(409, "DEMO_SCENARIO_RESET_CONFLICT", "演示状态正在更新，请重试复位。")
    return DemoScenarioResetResponse(
        scenario_id=result.scenario_id,
        status="READY",
        message=result.message,
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message},
    )
