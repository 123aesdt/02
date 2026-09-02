"""Bounded Docker security acceptance without printing tokens or credentials."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
import jwt
import websockets
from websockets.exceptions import ConnectionClosed, InvalidHandshake

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.security.permissions import ROLE_PERMISSION_MATRIX, Role

ROLE_NAMES = ("DISPATCHER", "SUPERVISOR", "OPERATOR", "AUDITOR", "ADMIN")
CONFIG_KEYS = frozenset({"DEVELOPMENT_JWT_SECRET", "AUTH_ISSUER", "AUTH_AUDIENCE"})
OVERRIDE_PAYLOAD = {
    "idempotency_key": "security-integration-override",
    "entity_type": "Vehicle",
    "entity_id": "vehicle-001",
    "field": "status",
    "old_value": "NORMAL",
    "new_value": "BROKEN",
    "reason": "bounded security integration permission probe",
    "expected_version": 7,
    "expected_next_node": "capacity",
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify authenticated HTTP and WebSocket controls against the real Docker backend."
    )
    parser.add_argument("--api-base-url", default=os.getenv("E2E_API_BASE_URL", "http://localhost:8001"))
    parser.add_argument("--ws-base-url", default=os.getenv("E2E_WS_BASE_URL", "ws://localhost:8001"))
    return parser.parse_args()


def ignored_config() -> dict[str, str]:
    values = {key: os.getenv(key, "").strip() for key in CONFIG_KEYS}
    env_file = PROJECT_ROOT / ".docker.env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in CONFIG_KEYS and not values[key]:
                values[key] = value.strip()
    if len(values["DEVELOPMENT_JWT_SECRET"]) < 32:
        raise RuntimeError("Ignored Docker development signing configuration is unavailable")
    return values


def development_token(
    role: Role,
    config: dict[str, str],
    *,
    now: datetime | None = None,
    ttl_seconds: int = 300,
) -> str:
    issued_at = now or datetime.now(UTC)
    return jwt.encode(
        {
            "iss": config["AUTH_ISSUER"] or "countyflow-dev",
            "aud": config["AUTH_AUDIENCE"] or "countyflow-api",
            "sub": f"security-e2e-{role.value.lower()}-{uuid4().hex}",
            "name": f"Security E2E {role.value.title()}",
            "roles": [role.value],
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + timedelta(seconds=ttl_seconds),
            "jti": uuid4().hex,
        },
        config["DEVELOPMENT_JWT_SECRET"],
        algorithm="HS256",
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_status(response: httpx.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{label} returned an unexpected status")


async def verify_role_matrix(
    client: httpx.AsyncClient,
    config: dict[str, str],
) -> dict[Role, str]:
    tokens = {role: development_token(role, config) for role in Role}
    for role, token in tokens.items():
        response = await client.get("/api/v1/auth/me", headers=bearer(token))
        assert_status(response, 200, f"{role.value} identity")
        body = response.json()
        if body.get("roles") != [role.value]:
            raise RuntimeError(f"{role.value} identity did not preserve its role")
        actual = set(body.get("permissions", []))
        expected = {permission.value for permission in ROLE_PERMISSION_MATRIX[role]}
        if actual != expected:
            raise RuntimeError(f"{role.value} permission projection differs from the approved matrix")

    dispatcher = bearer(tokens[Role.DISPATCHER])
    assert_status(
        await client.get("/api/v1/observability/summary", headers=dispatcher),
        403,
        "Dispatcher monitoring denial",
    )
    assert_status(
        await client.post(
            "/api/v1/runtime/threads/security-missing/overrides",
            headers=dispatcher,
            json=OVERRIDE_PAYLOAD,
        ),
        403,
        "Dispatcher direct override bypass",
    )

    supervisor = bearer(tokens[Role.SUPERVISOR])
    assert_status(
        await client.get("/api/v1/observability/summary", headers=supervisor),
        200,
        "Supervisor monitoring",
    )
    supervisor_override = await client.post(
        "/api/v1/runtime/threads/security-missing/overrides",
        headers=supervisor,
        json={**OVERRIDE_PAYLOAD, "idempotency_key": f"security-supervisor-{uuid4().hex}"},
    )
    if supervisor_override.status_code == 403:
        raise RuntimeError("Supervisor override permission was denied")

    operator = bearer(tokens[Role.OPERATOR])
    assert_status(
        await client.get("/api/v1/observability/summary", headers=operator),
        200,
        "Operator monitoring",
    )
    assert_status(
        await client.get("/api/v1/memory/facts/security-missing", headers=operator),
        403,
        "Operator memory denial",
    )

    auditor = bearer(tokens[Role.AUDITOR])
    assert_status(await client.get("/api/v1/security/audit", headers=auditor), 200, "Auditor audit read")
    assert_status(
        await client.post(
            "/api/v1/dispatch-tasks",
            headers=auditor,
            json=dispatch_payload(),
        ),
        403,
        "Auditor dispatch denial",
    )

    admin = bearer(tokens[Role.ADMIN])
    assert_status(await client.get("/api/v1/observability/summary", headers=admin), 200, "Admin monitoring")
    assert_status(await client.get("/api/v1/security/audit", headers=admin), 200, "Admin audit")
    return tokens


def dispatch_payload() -> dict[str, object]:
    return {
        "order_id": 1,
        "anomaly_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "bounded V2-G2 security acceptance",
        "idempotency_key": f"security-e2e-{uuid4().hex}",
    }


async def verify_expiry_and_revocation(client: httpx.AsyncClient, config: dict[str, str]) -> None:
    expired = development_token(
        Role.OPERATOR,
        config,
        now=datetime.now(UTC) - timedelta(minutes=2),
        ttl_seconds=1,
    )
    responses = await asyncio.gather(
        *(client.get("/api/v1/auth/me", headers=bearer(expired)) for _ in range(6))
    )
    status_codes = {response.status_code for response in responses}
    if not status_codes.issubset({401, 429}) or 401 not in status_codes:
        raise RuntimeError("Expired-token request handling was not bounded")

    token = development_token(Role.AUDITOR, config)
    headers = bearer(token)
    assert_status(await client.get("/api/v1/auth/me", headers=headers), 200, "Pre-logout identity")
    assert_status(await client.post("/api/v1/auth/logout", headers=headers), 204, "Logout")
    assert_status(await client.get("/api/v1/auth/me", headers=headers), 401, "Revoked token")


async def verify_override_rate_limit(client: httpx.AsyncClient, config: dict[str, str]) -> None:
    headers = bearer(development_token(Role.SUPERVISOR, config))

    async def attempt(index: int) -> int:
        response = await client.post(
            "/api/v1/runtime/threads/security-rate-missing/overrides",
            headers=headers,
            json={**OVERRIDE_PAYLOAD, "idempotency_key": f"security-rate-{index}-{uuid4().hex}"},
        )
        return response.status_code

    statuses = await asyncio.gather(*(attempt(index) for index in range(12)))
    if 429 not in statuses or any(status >= 500 for status in statuses):
        raise RuntimeError("Concurrent override abuse was not bounded by HTTP 429")


async def expect_ws_close(uri: str, expected_code: int) -> None:
    try:
        async with websockets.connect(uri, open_timeout=5) as socket:
            await asyncio.wait_for(socket.recv(), timeout=5)
    except ConnectionClosed as error:
        if error.code != expected_code:
            raise RuntimeError("WebSocket security close code differed from the contract") from None
        return
    except (InvalidHandshake, OSError, TimeoutError):
        raise RuntimeError("WebSocket security handshake failed without the required close code") from None
    raise RuntimeError("WebSocket security denial unexpectedly opened a usable stream")


async def issue_ticket(client: httpx.AsyncClient, token: str, task_id: str) -> str:
    response = await client.post(
        "/api/v1/ws-tickets",
        headers=bearer(token),
        json={"target_type": "task", "target_id": task_id},
    )
    assert_status(response, 201, "WebSocket ticket issuance")
    ticket = response.json().get("ticket")
    if not isinstance(ticket, str) or not ticket:
        raise RuntimeError("WebSocket ticket was absent")
    return ticket


async def verify_ws_tickets(
    client: httpx.AsyncClient,
    ws_base_url: str,
    dispatcher_token: str,
) -> None:
    accepted = await client.post(
        "/api/v1/dispatch-tasks",
        headers=bearer(dispatcher_token),
        json=dispatch_payload(),
    )
    assert_status(accepted, 202, "Security WebSocket task creation")
    task_id = accepted.json().get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise RuntimeError("Security WebSocket task id was absent")

    scoped_ticket = await issue_ticket(client, dispatcher_token, task_id)
    wrong_scope = (
        f"{ws_base_url}/api/v1/ws/tasks/{task_id}-wrong"
        f"?ticket={quote(scoped_ticket, safe='')}"
    )
    await expect_ws_close(wrong_scope, 4403)

    replay_ticket = await issue_ticket(client, dispatcher_token, task_id)
    correct = f"{ws_base_url}/api/v1/ws/tasks/{task_id}?ticket={quote(replay_ticket, safe='')}"
    async with websockets.connect(correct, open_timeout=5) as socket:
        snapshot = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        if snapshot.get("event_type") != "TASK_SNAPSHOT":
            raise RuntimeError("Authenticated WebSocket did not provide a task snapshot")
    await expect_ws_close(correct, 4408)


async def verify(api_base_url: str, ws_base_url: str) -> dict[str, object]:
    config = ignored_config()
    async with httpx.AsyncClient(base_url=api_base_url, timeout=8) as client:
        health = await client.get("/health")
        anonymous = await client.get("/api/v1/auth/me")
        assert_status(health, 200, "Docker backend health")
        assert_status(anonymous, 401, "Anonymous identity denial")
        if anonymous.json().get("code") != "AUTHENTICATION_REQUIRED":
            raise RuntimeError("Anonymous denial did not use the stable authentication code")

        tokens = await verify_role_matrix(client, config)
        await verify_expiry_and_revocation(client, config)
        await verify_override_rate_limit(client, config)
        await verify_ws_tickets(client, ws_base_url, tokens[Role.DISPATCHER])

        audit = await client.get("/api/v1/security/audit", headers=bearer(tokens[Role.ADMIN]))
        assert_status(audit, 200, "Final security audit read")
        serialized_audit = json.dumps(audit.json(), sort_keys=True)
        forbidden_values = [config["DEVELOPMENT_JWT_SECRET"], *tokens.values()]
        if any(value and value in serialized_audit for value in forbidden_values):
            raise RuntimeError("Security audit contained credential material")

    return {
        "roles": len(ROLE_NAMES),
        "anonymous_http": "DENIED",
        "direct_api_bypass": "DENIED",
        "revocation": "ENFORCED",
        "override_rate_limit": 429,
        "ws_scope_close": 4403,
        "ws_replay_close": 4408,
        "secrets_emitted": False,
    }


def main() -> int:
    values = arguments()
    try:
        result = asyncio.run(verify(values.api_base_url, values.ws_base_url))
    except (httpx.HTTPError, RuntimeError, ValueError) as error:
        print(f"Security integration failed: {type(error).__name__}", file=sys.stderr)
        return 1
    print("Security integration passed: " + ", ".join(f"{key}={value}" for key, value in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
