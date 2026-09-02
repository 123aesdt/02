from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.security.permissions import Permission, Role


class AuthMethod(StrEnum):
    OIDC_JWT = "oidc_jwt"
    DEVELOPMENT_JWT = "development_jwt"


def _required(value: str, name: str, maximum: int = 128) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return normalized


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject_id: str
    display_name: str
    roles: frozenset[Role]
    permissions: frozenset[Permission]
    auth_method: AuthMethod
    issued_at: datetime
    expires_at: datetime
    jti: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _required(self.subject_id, "subject_id"))
        object.__setattr__(self, "display_name", _required(self.display_name, "display_name", 256))
        object.__setattr__(self, "jti", _required(self.jti, "jti", 256))
        object.__setattr__(self, "roles", frozenset(Role(value) for value in self.roles))
        object.__setattr__(self, "permissions", frozenset(Permission(value) for value in self.permissions))
        object.__setattr__(self, "auth_method", AuthMethod(self.auth_method))
        issued_at = _aware(self.issued_at, "issued_at")
        expires_at = _aware(self.expires_at, "expires_at")
        if expires_at <= issued_at:
            raise ValueError("expires_at must be later than issued_at")

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def to_public_dict(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "display_name": self.display_name,
            "roles": sorted(role.value for role in self.roles),
            "permissions": sorted(permission.value for permission in self.permissions),
            "auth_method": self.auth_method.value,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }
