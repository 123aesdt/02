import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.security.models import AuthenticatedPrincipal, AuthMethod
from app.security.permissions import ROLE_PERMISSION_MATRIX, Role

DEVELOPMENT_ROLE_DISPLAY_NAMES: dict[Role, str] = {
    Role.EMPLOYEE: "CountyFlow 开发配送员工",
    Role.DISPATCHER: "CountyFlow 开发调度员",
    Role.SUPERVISOR: "CountyFlow 开发调度主管",
    Role.OPERATOR: "CountyFlow 开发系统运维",
    Role.AUDITOR: "CountyFlow 开发审计员",
    Role.ADMIN: "CountyFlow 开发管理员",
}


@dataclass(frozen=True)
class DevelopmentSession:
    access_token: str
    expires_in: int
    principal: AuthenticatedPrincipal


class DevelopmentSessionIssuer:
    def __init__(self, secret: str, *, issuer: str, audience: str, ttl_seconds: int) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._ttl_seconds = ttl_seconds

    def issue(self, role: Role) -> DevelopmentSession:
        return self.issue_identity(
            subject_id=f"dev-{role.value.lower()}",
            display_name=DEVELOPMENT_ROLE_DISPLAY_NAMES[role],
            role=role,
        )

    def issue_identity(self, *, subject_id: str, display_name: str, role: Role) -> DevelopmentSession:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        jti = uuid.uuid4().hex
        principal = AuthenticatedPrincipal(
            subject_id=subject_id,
            display_name=display_name,
            roles=frozenset({role}),
            permissions=ROLE_PERMISSION_MATRIX[role],
            auth_method=AuthMethod.DEVELOPMENT_JWT,
            issued_at=now,
            expires_at=expires_at,
            jti=jti,
        )
        access_token = jwt.encode(
            {
                "iss": self._issuer,
                "aud": self._audience,
                "sub": principal.subject_id,
                "name": principal.display_name,
                "roles": [role.value],
                "iat": now,
                "nbf": now,
                "exp": expires_at,
                "jti": jti,
            },
            self._secret,
            algorithm="HS256",
        )
        return DevelopmentSession(access_token=access_token, expires_in=self._ttl_seconds, principal=principal)

    def issue_admin(self) -> DevelopmentSession:
        return self.issue(Role.ADMIN)
