from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events.broker import EventBrokerConnectionError, TaskEventBroker
from app.events.models import TaskEvent, TaskEventType
from app.events.visibility import TaskEventVisibilityProjector
from app.observability.websocket import event_group
from app.security.audit import SecurityAuditEventType, SecurityAuditStatus
from app.security.metrics import record_security_metric
from app.security.permissions import Permission
from app.security.security_audit import SecurityAuditUnavailable
from app.security.ws_ticket import WsTicketRejected, WsTicketUnavailable
from app.services.dispatch_task_api_service import TaskNotFoundError

router = APIRouter(prefix="/api/v1/ws/tasks", tags=["task-events"])


@router.websocket("/{task_id}")
async def task_events(websocket: WebSocket, task_id: str) -> None:
    service = websocket.app.state.dispatch_task_api_service
    broker: TaskEventBroker = websocket.app.state.task_event_broker
    ticket = websocket.query_params.get("ticket")
    if ticket is None:
        _audit_ticket_rejection(websocket, "WS_TICKET_MISSING")
        await _close_with_visible_code(websocket, 4401)
        return
    try:
        consumed_ticket = await websocket.app.state.ws_ticket_service.consume(
            ticket,
            target_type="task",
            target_id=task_id,
            required_permission=Permission.DISPATCH_READ,
        )
    except WsTicketUnavailable:
        _audit_ticket_rejection(websocket, "SECURITY_CONTROL_UNAVAILABLE")
        await _close_with_visible_code(websocket, 1011)
        return
    except WsTicketRejected as error:
        _audit_ticket_rejection(websocket, error.code)
        close_code = {
            "WS_TICKET_WRONG_SCOPE": 4403,
            "WS_TICKET_PERMISSION_DENIED": 4403,
            "WS_TICKET_REPLAYED_OR_EXPIRED": 4408,
        }.get(error.code, 4401)
        await _close_with_visible_code(websocket, close_code)
        return
    try:
        status = service.status(task_id)
    except TaskNotFoundError:
        await _close_with_visible_code(websocket, 1008)
        return

    projector = TaskEventVisibilityProjector(service._session_factory)
    await websocket.accept()
    metrics = websocket.app.state.metrics_recorder
    metrics.adjust_gauge("countyflow_websocket_connections", 1)
    subscription = None
    try:
        snapshot = TaskEvent.create(
            task_id,
            TaskEventType.TASK_SNAPSHOT,
            "snapshot",
            str(status["status"]),
            data={"ready": status["ready"], "requires_manual_review": status["requires_manual_review"]},
        )
        await _send_projected(websocket, projector, snapshot, can_review=consumed_ticket.can_review)
        metrics.increment("countyflow_websocket_events_total", {"event_type": "task", "result": "sent"})
        last_event_id = websocket.query_params.get("last_event_id")
        replay = await broker.history(task_id, after_event_id=last_event_id)
        cursor = replay[-1].event_id if replay else last_event_id
        subscription = await broker.subscribe(task_id, last_event_id=cursor)
        for event in replay:
            await _send_projected(websocket, projector, event, can_review=consumed_ticket.can_review)
            metrics.increment("countyflow_websocket_events_total", {"event_type": event_group(event.event_type), "result": "replayed"})
        while True:
            for event in await subscription.read():
                await _send_projected(websocket, projector, event, can_review=consumed_ticket.can_review)
                metrics.increment("countyflow_websocket_events_total", {"event_type": event_group(event.event_type), "result": "sent"})
    except EventBrokerConnectionError:
        metrics.increment("countyflow_websocket_events_total", {"event_type": "task", "result": "error"})
        await websocket.close(code=1011)
        return
    except WebSocketDisconnect:
        return
    finally:
        if subscription is not None:
            await broker.unsubscribe(subscription)
        metrics.adjust_gauge("countyflow_websocket_connections", -1)


async def _send_projected(
    websocket: WebSocket,
    projector: TaskEventVisibilityProjector,
    event: TaskEvent,
    *,
    can_review: bool,
) -> None:
    await websocket.send_json(projector.project(event, can_review=can_review))


async def _close_with_visible_code(websocket: WebSocket, code: int) -> None:
    """Complete the handshake so browser clients receive the bounded close code."""
    await websocket.accept()
    await websocket.close(code=code)


def _audit_ticket_rejection(websocket: WebSocket, reason_code: str) -> None:
    metric_reason = {
        "WS_TICKET_MISSING": "missing",
        "WS_TICKET_WRONG_SCOPE": "wrong_scope",
        "WS_TICKET_PERMISSION_DENIED": "permission",
        "WS_TICKET_REPLAYED_OR_EXPIRED": "expired_replayed",
        "SECURITY_CONTROL_UNAVAILABLE": "control_unavailable",
    }.get(reason_code, "invalid")
    record_security_metric(
        getattr(websocket.app.state, "metrics_recorder", None),
        "countyflow_ws_ticket_rejected_total",
        reason_code=metric_reason,
        path=websocket.url.path,
    )
    recorder = getattr(websocket.app.state, "security_audit_recorder", None)
    if recorder is None:
        return
    try:
        recorder.record(
            websocket,
            event_type=SecurityAuditEventType.WS_TICKET_REJECTED,
            status=SecurityAuditStatus.DENIED,
            reason_code=reason_code,
            principal=None,
            permission=Permission.DISPATCH_READ,
        )
    except SecurityAuditUnavailable:
        pass
