from enum import StrEnum
from typing import Protocol

from app.security.models import AuthenticatedPrincipal


class AuthenticationErrorCode(StrEnum):
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"


class AuthenticationError(Exception):
    def __init__(self, code: AuthenticationErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class AuthenticationProviderUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("AUTHENTICATION_UNAVAILABLE")


class AuthenticationProvider(Protocol):
    async def authenticate(self, token: str) -> AuthenticatedPrincipal: ...


class RevocationStore(Protocol):
    async def is_revoked(self, jti: str) -> bool: ...

