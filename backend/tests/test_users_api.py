"""Tests for admin user management and the manager-facing user directory."""

import pytest
from httpx import AsyncClient

from support import AuthHeaders, UserFactory
from time_reporting.modules.users.contracts import UserRole


async def test_worker_cannot_list_or_search_users(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(role=UserRole.WORKER))

    assert (await client.get("/api/v1/users", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/users/directory", headers=headers)).status_code == 403


async def test_admin_can_search_users_by_name_or_email(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    headers = auth_headers(admin)
    match = await make_user(name="Findable Person", email="findable@example.com")
    await make_user(name="Someone Else", email="someone-else@example.com")

    response = await client.get("/api/v1/users", headers=headers, params={"search": "findable"})

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(match.id) in ids
    assert str(admin.id) not in ids


async def test_admin_list_users_can_exclude_inactive(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    headers = auth_headers(admin)
    inactive = await make_user(name="Inactive Person", email="inactive-listed@example.com")
    await client.patch(f"/api/v1/users/{inactive.id}", headers=headers, json={"is_active": False})

    response = await client.get(
        "/api/v1/users",
        headers=headers,
        params={"search": "Inactive Person", "include_inactive": False},
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.PROJECT_MANAGER])
async def test_manager_can_search_the_user_directory(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders, role: UserRole
) -> None:
    headers = auth_headers(await make_user(role=role))
    active = await make_user(name="Directory Person", email="directory-person@example.com")
    inactive = await make_user(name="Directory Inactive", email="directory-inactive@example.com")
    admin_headers = auth_headers(await make_user(role=UserRole.ADMIN))
    await client.patch(
        f"/api/v1/users/{inactive.id}", headers=admin_headers, json={"is_active": False}
    )

    response = await client.get(
        "/api/v1/users/directory", headers=headers, params={"search": "Directory"}
    )

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body}
    assert str(active.id) in ids
    assert str(inactive.id) not in ids
    assert set(body[0].keys()) == {"id", "name", "email", "role"}


async def test_user_directory_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/users/directory")).status_code == 401


async def test_user_directory_can_filter_by_role(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin = await make_user(role=UserRole.ADMIN, name="Ada Admin", email="ada-admin@example.com")
    manager = await make_user(
        role=UserRole.PROJECT_MANAGER, name="Mark Manager", email="mark-manager@example.com"
    )
    worker = await make_user(role=UserRole.WORKER, name="Wendy Worker", email="wendy@example.com")
    headers = auth_headers(admin)

    response = await client.get(
        "/api/v1/users/directory",
        headers=headers,
        params={"role": ["admin", "project_manager"]},
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {str(admin.id), str(manager.id)}
    assert str(worker.id) not in ids
