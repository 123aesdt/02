from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    DISPATCHER = "DISPATCHER"
    SUPERVISOR = "SUPERVISOR"
    OPERATOR = "OPERATOR"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"


class Permission(StrEnum):
    DISPATCH_READ = "dispatch:read"
    DISPATCH_CREATE = "dispatch:create"
    DISPATCH_REVIEW = "dispatch:review"
    ORDERS_READ = "orders:read"
    ANOMALIES_READ = "anomalies:read"
    ANOMALIES_REPORT = "anomalies:report"
    AGENTS_READ = "agents:read"
    MEMORY_READ = "memory:read"
    MEMORY_MUTATE = "memory:mutate"
    RUNTIME_READ = "runtime:read"
    RUNTIME_OVERRIDE = "runtime:override"
    AUDIT_READ = "audit:read"
    MONITOR_READ = "monitor:read"
    SYSTEM_ADMIN = "system:admin"


ALL_PERMISSIONS = frozenset(Permission)


def _matrix() -> dict[Role, frozenset[Permission]]:
    dispatcher = frozenset(
        {
            Permission.DISPATCH_READ,
            Permission.DISPATCH_CREATE,
            Permission.ORDERS_READ,
            Permission.ANOMALIES_READ,
            Permission.AGENTS_READ,
            Permission.MEMORY_READ,
        }
    )
    return {
        Role.EMPLOYEE: frozenset({Permission.DISPATCH_READ, Permission.ANOMALIES_REPORT}),
        Role.DISPATCHER: dispatcher,
        Role.SUPERVISOR: dispatcher
        | {
            Permission.DISPATCH_REVIEW,
            Permission.MEMORY_MUTATE,
            Permission.RUNTIME_READ,
            Permission.RUNTIME_OVERRIDE,
            Permission.AUDIT_READ,
            Permission.MONITOR_READ,
        },
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


ROLE_PERMISSION_MATRIX = _matrix()


def permissions_for_roles(values: list[str] | tuple[str, ...]) -> tuple[frozenset[Permission], tuple[str, ...]]:
    permissions: set[Permission] = set()
    unknown: list[str] = []
    for value in values:
        try:
            role = Role(value)
        except ValueError:
            unknown.append(value)
            continue
        permissions.update(ROLE_PERMISSION_MATRIX[role])
    return frozenset(permissions), tuple(unknown)
