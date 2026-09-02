import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.security.jwt_provider import DevelopmentJwtProvider, HttpJwksKeyResolver, OidcJwtProvider
from app.security.models import AuthMethod, Role
from app.security.permissions import Permission
from app.security.protocols import AuthenticationError, AuthenticationErrorCode, AuthenticationProviderUnavailable


def _encode(value: dict[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def token(secret: str, claims: dict[str, object], *, algorithm: str = "HS256") -> str:
    header = _encode({"alg": algorithm, "typ": "JWT"})
    payload = _encode(claims)
    signing_input = f"{header}.{payload}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest() if algorithm == "HS256" else b""
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{encoded_signature}"


def claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    value: dict[str, object] = {
        "iss": "countyflow-dev",
        "aud": "countyflow-api",
        "sub": "dispatcher-1",
        "name": "Dispatch User",
        "roles": ["DISPATCHER"],
        "iat": int(now.timestamp()),
        "nbf": int((now - timedelta(seconds=1)).timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": "session-1",
    }
    value.update(overrides)
    return value


class Revocations:
    def __init__(self, revoked: bool = False) -> None:
        self.revoked = revoked

    async def is_revoked(self, jti: str) -> bool:
        return self.revoked


@pytest.mark.asyncio
async def test_development_provider_returns_typed_principal_for_valid_token() -> None:
    secret = "development-secret-value-32-chars"
    provider = DevelopmentJwtProvider(secret, issuer="countyflow-dev", audience="countyflow-api", revocations=Revocations())

    principal = await provider.authenticate(token(secret, claims()))

    assert principal.subject_id == "dispatcher-1"
    assert principal.auth_method is AuthMethod.DEVELOPMENT_JWT
    assert principal.roles == frozenset({Role.DISPATCHER})
    assert principal.permissions == frozenset(
        {
            Permission.DISPATCH_READ,
            Permission.DISPATCH_CREATE,
            Permission.ORDERS_READ,
            Permission.ANOMALIES_READ,
            Permission.AGENTS_READ,
            Permission.MEMORY_READ,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_token", "expected"),
    [
        ("not-a-jwt", AuthenticationErrorCode.TOKEN_INVALID),
        (token("wrong-secret-value-with-32-chars", claims()), AuthenticationErrorCode.TOKEN_INVALID),
        (token("development-secret-value-32-chars", claims(exp=1)), AuthenticationErrorCode.TOKEN_EXPIRED),
        (
            token("development-secret-value-32-chars", claims(aud="another-api")),
            AuthenticationErrorCode.TOKEN_INVALID,
        ),
        (
            token("development-secret-value-32-chars", claims(iss="another-issuer")),
            AuthenticationErrorCode.TOKEN_INVALID,
        ),
        (token("development-secret-value-32-chars", claims(), algorithm="none"), AuthenticationErrorCode.TOKEN_INVALID),
    ],
)
async def test_invalid_token_is_denied_without_sensitive_detail(raw_token: str, expected: AuthenticationErrorCode) -> None:
    provider = DevelopmentJwtProvider(
        "development-secret-value-32-chars",
        issuer="countyflow-dev",
        audience="countyflow-api",
        revocations=Revocations(),
    )

    with pytest.raises(AuthenticationError) as captured:
        await provider.authenticate(raw_token)

    assert captured.value.code is expected
    assert raw_token not in str(captured.value)


@pytest.mark.asyncio
async def test_client_role_claim_cannot_escalate_permissions() -> None:
    secret = "development-secret-value-32-chars"
    provider = DevelopmentJwtProvider(secret, issuer="countyflow-dev", audience="countyflow-api", revocations=Revocations())
    raw = token(secret, claims(permissions=["system:admin", "runtime:override"], roles=["DISPATCHER", "ROOT"]))

    principal = await provider.authenticate(raw)

    assert principal.roles == frozenset({Role.DISPATCHER})
    assert Permission.SYSTEM_ADMIN not in principal.permissions
    assert Permission.RUNTIME_OVERRIDE not in principal.permissions


@pytest.mark.asyncio
async def test_revoked_token_is_denied() -> None:
    secret = "development-secret-value-32-chars"
    provider = DevelopmentJwtProvider(secret, issuer="countyflow-dev", audience="countyflow-api", revocations=Revocations(True))

    with pytest.raises(AuthenticationError) as captured:
        await provider.authenticate(token(secret, claims()))

    assert captured.value.code is AuthenticationErrorCode.TOKEN_REVOKED


@pytest.mark.asyncio
async def test_auth_provider_failure_fails_closed() -> None:
    class FailedRevocations:
        async def is_revoked(self, jti: str) -> bool:
            raise AuthenticationProviderUnavailable

    secret = "development-secret-value-32-chars"
    provider = DevelopmentJwtProvider(secret, issuer="countyflow-dev", audience="countyflow-api", revocations=FailedRevocations())

    with pytest.raises(AuthenticationProviderUnavailable):
        await provider.authenticate(token(secret, claims()))


def _rsa_material() -> tuple[object, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-1", "alg": "RS256", "use": "sig"})
    return private_key, public_jwk


@pytest.mark.asyncio
async def test_oidc_provider_validates_rs256_kid_issuer_and_audience() -> None:
    private_key, public_jwk = _rsa_material()

    class Resolver:
        async def resolve(self, kid: str, algorithm: str) -> object:
            assert kid == "key-1"
            assert algorithm == "RS256"
            return jwt.algorithms.RSAAlgorithm.from_jwk(public_jwk)

    raw = jwt.encode(claims(iss="https://identity.example.test/"), private_key, algorithm="RS256", headers={"kid": "key-1"})
    provider = OidcJwtProvider(
        Resolver(),
        issuer="https://identity.example.test/",
        audience="countyflow-api",
        algorithms=("RS256",),
        revocations=Revocations(),
    )

    principal = await provider.authenticate(raw)

    assert principal.auth_method is AuthMethod.OIDC_JWT
    assert principal.subject_id == "dispatcher-1"


@pytest.mark.asyncio
async def test_oidc_algorithm_allowlist_cannot_be_broadened_by_token_header() -> None:
    class Resolver:
        async def resolve(self, kid: str, algorithm: str) -> object:
            raise AssertionError("resolver must not run for disallowed algorithms")

    provider = OidcJwtProvider(
        Resolver(),
        issuer="https://identity.example.test/",
        audience="countyflow-api",
        algorithms=("RS256",),
        revocations=Revocations(),
    )

    with pytest.raises(AuthenticationError) as captured:
        await provider.authenticate(token("development-secret-value-32-chars", claims(), algorithm="HS256"))

    assert captured.value.code is AuthenticationErrorCode.TOKEN_INVALID


@pytest.mark.asyncio
async def test_http_jwks_resolver_caches_known_key_and_refreshes_unknown_kid_once() -> None:
    _private_key, public_jwk = _rsa_material()
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={"keys": [public_jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resolver = HttpJwksKeyResolver("https://identity.example.test/jwks", client=client, cache_ttl_seconds=300)
        first = await resolver.resolve("key-1", "RS256")
        second = await resolver.resolve("key-1", "RS256")
        assert first is second
        assert requests == 1

        with pytest.raises(AuthenticationError) as captured:
            await resolver.resolve("unknown", "RS256")

    assert captured.value.code is AuthenticationErrorCode.TOKEN_INVALID
    assert requests == 2


@pytest.mark.asyncio
async def test_oidc_jwks_failure_fails_closed() -> None:
    class Resolver:
        async def resolve(self, kid: str, algorithm: str) -> object:
            raise AuthenticationProviderUnavailable

    private_key, _public_jwk = _rsa_material()
    raw = jwt.encode(claims(iss="https://identity.example.test/"), private_key, algorithm="RS256", headers={"kid": "key-1"})
    provider = OidcJwtProvider(
        Resolver(),
        issuer="https://identity.example.test/",
        audience="countyflow-api",
        algorithms=("RS256",),
        revocations=Revocations(),
    )

    with pytest.raises(AuthenticationProviderUnavailable):
        await provider.authenticate(raw)
