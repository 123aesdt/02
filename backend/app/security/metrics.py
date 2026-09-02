from app.observability.recorder import MetricsRecorder


def security_route_class(path: str) -> str:
    if path.startswith("/api/v1/auth"):
        return "auth"
    if path.startswith("/api/v1/dispatch"):
        return "dispatch"
    if path.startswith("/api/v1/runtime"):
        return "runtime"
    if path.startswith("/api/v1/memory"):
        return "memory"
    if path.startswith("/api/v1/observability"):
        return "observability"
    if path.startswith("/api/v1/security/audit"):
        return "audit"
    if path.startswith("/api/v1/ws"):
        return "websocket"
    return "other"


def record_security_metric(
    recorder: MetricsRecorder | None,
    family: str,
    *,
    reason_code: str,
    path: str,
) -> None:
    if recorder is None:
        return
    try:
        recorder.increment(
            family,
            {"reason_code": reason_code, "route_class": security_route_class(path)},
        )
    except Exception:
        return
