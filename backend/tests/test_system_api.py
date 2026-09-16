import pytest
from httpx import AsyncClient

from support import ADMIN, EMPLOYEE, MANAGER, AuthHeaders, UserFactory
from time_reporting.modules.users.contracts import UserRole


async def test_anonymous_cannot_get_system_status(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/system/status")

    assert response.status_code == 401


@pytest.mark.parametrize("roles", [MANAGER, EMPLOYEE])
async def test_non_admin_cannot_use_system_routes(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    responses = [
        await client.get("/api/v1/admin/system/status", headers=headers),
        await client.get("/api/v1/admin/system/config", headers=headers),
    ]

    assert {r.status_code for r in responses} == {403}


async def test_admin_can_get_system_status(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.get("/api/v1/admin/system/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["backend_version"]
    assert body["uptime_seconds"] >= 0
    database = body["database"]
    assert database["server_version"]
    assert database["size_bytes"] > 0
    assert database["connection_count"] >= 1
    assert database["current_revision"] == database["head_revision"]
    assert database["migrations_pending"] is False
    assert any(table["name"] == "users" for table in body["tables"])


async def test_admin_can_get_system_config_without_secrets(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    response = await client.get("/api/v1/admin/system/config", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert "jwt_secret_key" not in body
    assert "database_url" not in body
    assert set(body) == {
        "app_name",
        "debug",
        "cors_origins",
        "access_token_expire_minutes",
        "auth_cookie_secure",
        "holiday_country",
        "holiday_subdivision",
        "daily_working_hours",
    }
