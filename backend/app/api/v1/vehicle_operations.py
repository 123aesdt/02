from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from app.security.dependencies import require_permission
from app.security.models import AuthenticatedPrincipal
from app.security.permissions import Permission
from app.vehicle_operations.models import InvalidStateTransition
from app.vehicle_operations.sqlalchemy_repository import VehicleOperationNotFound, VehicleOperationsConflict

router = APIRouter(prefix="/api/v1", tags=["vehicle-operations"])


class InspectionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool


def get_service(request: Request):
    return request.app.state.vehicle_operations_api_service


Service = Annotated[object, Depends(get_service)]
Supervisor = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.DISPATCH_REVIEW))]
Driver = Annotated[AuthenticatedPrincipal, Depends(require_permission(Permission.ANOMALIES_REPORT))]


def _call(operation):
    try:
        return operation()
    except VehicleOperationNotFound as error:
        raise HTTPException(404, detail={"code": "VEHICLE_OPERATION_NOT_FOUND"}) from error
    except (VehicleOperationsConflict, InvalidStateTransition) as error:
        raise HTTPException(409, detail={"code": "VEHICLE_OPERATION_CONFLICT", "message": str(error)}) from error


@router.get("/map/snapshot")
def map_snapshot(service: Service, _principal: Supervisor, task_id: Annotated[str, Query(min_length=1, max_length=36)]):
    return _call(lambda: service.map_snapshot(task_id))


@router.get("/driver/operation-snapshot")
def driver_operation_snapshot(
    service: Service,
    principal: Driver,
    task_id: Annotated[str, Query(min_length=1, max_length=36)],
):
    return _call(lambda: service.driver_map_snapshot(task_id, principal))


@router.get("/fleet/vehicles")
def list_vehicles(service: Service, _principal: Supervisor):
    return _call(service.list_vehicles)


@router.get("/rescue-missions/{mission_no}")
def get_rescue_mission(mission_no: str, service: Service, _principal: Supervisor):
    return _call(lambda: service.get_rescue_mission(mission_no))


@router.post("/rescue-missions/{mission_no}/retry")
def retry_rescue_mission(mission_no: str, service: Service, _principal: Supervisor):
    return _call(lambda: service.retry_rescue_mission(mission_no))


@router.get("/maintenance-orders")
def list_maintenance_orders(service: Service, _principal: Supervisor):
    return _call(service.list_maintenance_orders)


@router.get("/maintenance-orders/{order_no}")
def get_maintenance_order(order_no: str, service: Service, _principal: Supervisor):
    return _call(lambda: service.get_maintenance_order(order_no))


@router.post("/maintenance-orders/{order_no}/inspection-decisions")
def inspection_decision(order_no: str, body: InspectionDecisionRequest, service: Service, principal: Supervisor):
    return _call(lambda: service.record_inspection(order_no, body.passed, principal))
