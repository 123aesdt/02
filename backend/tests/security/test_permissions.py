from app.security.models import Role
from app.security.permissions import ALL_PERMISSIONS, ROLE_PERMISSION_MATRIX, Permission, permissions_for_roles


def test_role_permission_matrix_matches_approved_contract() -> None:
    assert ROLE_PERMISSION_MATRIX == {
        Role.EMPLOYEE: frozenset({Permission.DISPATCH_READ, Permission.ANOMALIES_REPORT}),
        Role.DISPATCHER: frozenset(
            {
                Permission.DISPATCH_READ,
                Permission.DISPATCH_CREATE,
                Permission.ORDERS_READ,
                Permission.ANOMALIES_READ,
                Permission.AGENTS_READ,
                Permission.MEMORY_READ,
            }
        ),
        Role.SUPERVISOR: frozenset(
            {
                Permission.DISPATCH_READ,
                Permission.DISPATCH_CREATE,
                Permission.DISPATCH_REVIEW,
                Permission.ORDERS_READ,
                Permission.ANOMALIES_READ,
                Permission.AGENTS_READ,
                Permission.MEMORY_READ,
                Permission.MEMORY_MUTATE,
                Permission.RUNTIME_READ,
                Permission.RUNTIME_OVERRIDE,
                Permission.AUDIT_READ,
                Permission.MONITOR_READ,
            }
        ),
        Role.OPERATOR: frozenset(
            {
                Permission.AGENTS_READ,
                Permission.RUNTIME_READ,
                Permission.AUDIT_READ,
                Permission.MONITOR_READ,
            }
        ),
        Role.AUDITOR: frozenset(
            {
                Permission.MEMORY_READ,
                Permission.RUNTIME_READ,
                Permission.AUDIT_READ,
                Permission.MONITOR_READ,
            }
        ),
        Role.ADMIN: ALL_PERMISSIONS,
    }


def test_role_matrix_prevents_privilege_escalation() -> None:
    assert Permission.DISPATCH_READ in ROLE_PERMISSION_MATRIX[Role.EMPLOYEE]
    assert Permission.DISPATCH_CREATE not in ROLE_PERMISSION_MATRIX[Role.EMPLOYEE]
    assert Permission.RUNTIME_OVERRIDE in ROLE_PERMISSION_MATRIX[Role.SUPERVISOR]
    assert Permission.RUNTIME_OVERRIDE not in ROLE_PERMISSION_MATRIX[Role.DISPATCHER]
    assert Permission.MEMORY_MUTATE not in ROLE_PERMISSION_MATRIX[Role.AUDITOR]
    assert Permission.DISPATCH_CREATE not in ROLE_PERMISSION_MATRIX[Role.OPERATOR]
    assert Permission.SYSTEM_ADMIN not in ROLE_PERMISSION_MATRIX[Role.SUPERVISOR]
    assert ROLE_PERMISSION_MATRIX[Role.ADMIN] == ALL_PERMISSIONS


def test_employee_can_report_anomaly_without_dispatch_create() -> None:
    assert Permission.ANOMALIES_REPORT in ROLE_PERMISSION_MATRIX[Role.EMPLOYEE]
    assert Permission.DISPATCH_CREATE not in ROLE_PERMISSION_MATRIX[Role.EMPLOYEE]
    assert Permission.ANOMALIES_REPORT not in ROLE_PERMISSION_MATRIX[Role.DISPATCHER]
    assert ROLE_PERMISSION_MATRIX[Role.ADMIN] == ALL_PERMISSIONS


def test_unknown_role_claim_cannot_escalate_permissions() -> None:
    permissions, unknown = permissions_for_roles(["SUPERVISOR", "ROOT", "system:admin"])

    assert Permission.RUNTIME_OVERRIDE in permissions
    assert Permission.SYSTEM_ADMIN not in permissions
    assert unknown == ("ROOT", "system:admin")
