from fastapi.testclient import TestClient

from app.core.errors import OptimisticLockConflict
from app.main import create_app


def test_optimistic_lock_conflict_has_safe_http_409_response():
    app = create_app()

    @app.get("/_test-conflict")
    def raise_conflict():
        raise OptimisticLockConflict(dispatch_id=123)

    response = TestClient(app).get("/_test-conflict")

    assert response.status_code == 409
    assert response.json() == {
        "code": "DISPATCH_VERSION_CONFLICT",
        "message": "Dispatch was modified by another operation.",
        "details": {"dispatch_id": 123},
    }
