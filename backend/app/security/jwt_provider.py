import asyncio
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

import httpx
import jwt

from app.security.models import AuthenticatedPrincipal, AuthMethod, Role
from app.security.permissions import permissions_for_roles
from app.security.protocols import (
    AuthenticationError,
    AuthenticationErrorCode,
    AuthenticationProviderUnavailable,
    RevocationStore,
)


class DevelopmentJwtProvider:
    def __init__(
        self,
        secret: str,
        *,
        issuer: str,
        audience: str,
        revocations: RevocationStore,
        leeway_seconds: int = 30,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("development JWT secret must be at least 32 characters")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._revocations = revocations
        self._leeway_seconds = leeway_seconds

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_seconds,
                options={
                    "require": ["iss", "aud", "sub", "iat", "nbf", "exp", "jti"],
                    "verify_signature": True,
                },
            )
        except jwt.ExpiredSignatureError as error:
            raise AuthenticationError(AuthenticationErrorCode.TOKEN_EXPIRED) from error
        except jwt.PyJWTError as error:
            raise AuthenticationError(AuthenticationErrorCode.TOKEN_INVALID) from error
        try:
            principal = _principal(claims, AuthMethod.DEVELOPMENT_JWT)
            if await self._revocations.is_revoked(principal.jti):
                raise AuthenticationError(AuthenticationErrorCode.TOKEN_REVOKED)
            return principal
        except AuthenticationProviderUnavailable:
            raise
        except AuthenticationError:
            raise
        except (TypeError, ValueError, KeyError) as error:
            raise AuthenticationError(AuthenticationErrorCode.TOKEN_INVALID) from error



class SigningKeyResolver(Protocol):
    async def resolve(self, kid: str, algorithm: str) -> object: ...


class OidcJwtProvider:
    def __init__(
        self,
        resolver: SigningKeyResolver,
        *,
        issuer: str,
        audience: str,
        algorithms: tuple[str, ...],
        revocations: RevocationStore,
        leeway_seconds: int = 30,
    ) -> None:
        allowed = frozenset(algorithms)
        if not allowed or not allowed <= {"RS256", "ES256"}:
            raise ValueError("OIDC algorithms must be an RS256/ES256 allowlist")
        self._resolver = resolver
        self._issuer = issuer
        self._audience = audience
        self._algorithms = allowed
        self._revocations = revocations
        self._leeway_seconds = leeway_seconds

    async def authenticate(self, token: str) -> AuthenticatedPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")
            if algorithm not in self._algorithms or not isinstance(kid, str) or not kid.strip():
                raise AuthenticationError(AuthenticationErrorCode.TOKEN_INVALID)
            key = await self._resolver.resolve(kid, algorithm)
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_seconds,
                options={"require": ["iss", "aud", "sub", "iat", "nbf", "exp", "jti"]},
            )
            principal = _principal(claims, AuthMethod.OIDC_JWT)
            if await self._revocations.is_revoked(principal.jti):
                raise AuthenticationError(AuthenticationErrorCode.TOKEN_REVOKED)
            return principal
        except AuthenticationProviderUnavailable:
            raise
        except AuthenticationError:
            raise
        except jwt.ExpiredSignatureError as error:
            raise AuthenticationError(AuthenticationErrorCode.TOKEN_EXPIRED) from error
        except (jwt.PyJWTError, TypeError, ValueError, KeyError) as error:
            raise AuthenticationError(AuthenticationErrorCode.TOKEN_INVALID) from error


class HttpJwksKeyResolver:
    def __init__(
        self,
        url: str,
        *,
        client: httpx.AsyncClient | None = None,
        cache_ttl_seconds: float = 300,
        timeout_seconds: float = 1,
    ) -> None:
        self._url = url
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._timeout_seconds = timeout_seconds
        self._expires_at = 0.0
        self._keys: dict[tuple[str, str], object] = {}
        self._lock = asyncio.Lock()

    async def resolve(self, kid: str, algorithm: str) -> object:
        cache_key = (kid, algorithm)
        if time.monotonic() < self._expires_at and cache_key in self._keys:
            return self._keys[cache_key]
        async with self._lock:
            if time.monotonic() < self._expires_at and cache_key in self._keys:
                return self._keys[cache_key]
            await self._refresh()
            try:
                return self._keys[cache_key]
            except KeyError as error:
                raise AuthenticationError(AuthenticationErrorCode.TOKEN_INVALID) from error

    async def _refresh(self) -> None:
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(self._url)
            else:
                response = await self._client.get(self._url, timeout=self._timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            values = payload.get("keys") if isinstance(payload, dict) else None
            if not isinstance(values, list):
                raise ValueError("invalid JWKS shape")
            keys: dict[tuple[str, str], object] = {}
            for value in values:
                if not isinstance(value, dict):
                    continue
                kid = value.get("kid")
                algorithm = value.get("alg")
                if not isinstance(kid, str) or algorithm not in {"RS256", "ES256"}:
                    continue
                keys[(kid, algorithm)] = jwt.PyJWK.from_dict(value, algorithm=algorithm).key
            self._keys = keys
            self._expires_at = time.monotonic() + self._cache_ttl_seconds
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as error:
            raise AuthenticationProviderUnavailable from error


def _principal(claims: Mapping[str, object], auth_method: AuthMethod) -> AuthenticatedPrincipal:
    roles_value = claims.get("roles")
    if not isinstance(roles_value, list) or not all(isinstance(value, str) for value in roles_value):
        raise AuthenticationError(AuthenticationErrorCode.TOKEN_INVALID)
    permissions, _unknown = permissions_for_roles(tuple(roles_value))
    roles = frozenset(Role(value) for value in roles_value if value in Role._value2member_map_)
    if not roles:
        raise AuthenticationError(AuthenticationErrorCode.TOKEN_INVALID)
    issued_at = datetime.fromtimestamp(float(claims["iat"]), tz=UTC)
    expires_at = datetime.fromtimestamp(float(claims["exp"]), tz=UTC)
    subject = str(claims["sub"])
    display_name = str(claims.get("name") or subject)
    return AuthenticatedPrincipal(
        subject_id=subject,
        display_name=display_name,
        roles=roles,
        permissions=permissions,
        auth_method=auth_method,
        issued_at=issued_at,
        expires_at=expires_at,
        jti=str(claims["jti"]),
    )
