from app.security.models import AuthenticatedPrincipal
from app.security.protocols import AuthenticationError, AuthenticationErrorCode


class DisabledAuthenticationProvider:
    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        raise AuthenticationError(AuthenticationErrorCode.AUTHENTICATION_REQUIRED)

