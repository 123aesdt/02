import inspect

from app.runtime_overrides.service import RuntimeOverrideService
from app.security.permissions import Permission, Role
from tests.security_support import principal_for


def test_runtime_override_auth_required() -> None:
    principal = inspect.signature(RuntimeOverrideService.apply).parameters["principal"]

    assert principal.default is inspect.Parameter.empty


def test_supervisor_principal_owns_runtime_override_identity() -> None:
    principal = principal_for(Role.SUPERVISOR)

    assert principal.subject_id == "test-supervisor"
    assert principal.can(Permission.RUNTIME_OVERRIDE)


def test_runtime_override_permission_is_required() -> None:
    principal = principal_for(Role.OPERATOR)

    assert principal.can(Permission.RUNTIME_READ)
    assert not principal.can(Permission.RUNTIME_OVERRIDE)
