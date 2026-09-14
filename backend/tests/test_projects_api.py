from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from support import AuthHeaders, CustomerFactory, ProjectFactory, UserFactory
from time_reporting.modules.users.contracts import UserRole


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.PROJECT_MANAGER])
async def test_manager_full_project_lifecycle(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
    role: UserRole,
) -> None:
    headers = auth_headers(await make_user(role=role))
    customer = await make_customer()
    member = await make_user()

    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"customer_id": str(customer.id), "name": "Website Revamp"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Website Revamp"
    assert body["description"] is None
    assert body["is_active"] is True
    assert body["customer"]["id"] == str(customer.id)
    project_id = body["id"]

    patched = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=headers,
        json={"description": "Redesign the marketing site"},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Redesign the marketing site"
    assert patched.json()["name"] == "Website Revamp"

    added = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=headers,
        json={"user_id": str(member.id)},
    )
    assert added.status_code == 201
    assert added.json()["user_id"] == str(member.id)

    listed = await client.get(f"/api/v1/projects/{project_id}/members", headers=headers)
    assert listed.status_code == 200
    assert {m["user_id"] for m in listed.json()} == {str(member.id)}

    removed = await client.delete(
        f"/api/v1/projects/{project_id}/members/{member.id}", headers=headers
    )
    assert removed.status_code == 204

    listed_after_removal = await client.get(
        f"/api/v1/projects/{project_id}/members", headers=headers
    )
    assert listed_after_removal.json() == []


async def test_worker_can_read_but_not_write(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.WORKER))
    project = await make_project()
    url = f"/api/v1/projects/{project.id}"

    listed = await client.get("/api/v1/projects", headers=headers, params={"limit": 100})
    read = await client.get(url, headers=headers)
    members = await client.get(f"{url}/members", headers=headers)
    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"customer_id": str(project.customer.id), "name": "New"},
    )
    updated = await client.patch(url, headers=headers, json={"name": "Renamed"})
    added = await client.post(f"{url}/members", headers=headers, json={"user_id": str(uuid4())})
    removed = await client.delete(f"{url}/members/{uuid4()}", headers=headers)

    assert listed.status_code == 200
    assert str(project.id) in {item["id"] for item in listed.json()["items"]}
    assert read.status_code == 200
    assert members.status_code == 200
    assert created.status_code == 403
    assert updated.status_code == 403
    assert added.status_code == 403
    assert removed.status_code == 403


async def test_projects_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/projects")).status_code == 401
    assert (
        await client.post("/api/v1/projects", json={"customer_id": str(uuid4()), "name": "X"})
    ).status_code == 401


async def test_unknown_project_returns_404(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))
    url = f"/api/v1/projects/{uuid4()}"

    assert (await client.get(url, headers=headers)).status_code == 404
    assert (await client.patch(url, headers=headers, json={"name": "X"})).status_code == 404
    assert (await client.get(f"{url}/members", headers=headers)).status_code == 404
    assert (
        await client.post(f"{url}/members", headers=headers, json={"user_id": str(uuid4())})
    ).status_code == 404
    assert (await client.delete(f"{url}/members/{uuid4()}", headers=headers)).status_code == 404


async def test_create_for_unknown_or_archived_customer_returns_400(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))

    unknown = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"customer_id": str(uuid4()), "name": "Orphan"},
    )
    assert unknown.status_code == 400

    customer = await make_customer()
    await client.patch(
        f"/api/v1/customers/{customer.id}", headers=headers, json={"is_active": False}
    )
    archived = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"customer_id": str(customer.id), "name": "Too Late"},
    )
    assert archived.status_code == 400


async def test_duplicate_name_per_customer_returns_409(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))
    customer = await make_customer()
    payload: dict[str, Any] = {"customer_id": str(customer.id), "name": "Duplicate"}

    created = await client.post("/api/v1/projects", headers=headers, json=payload)
    duplicate = await client.post("/api/v1/projects", headers=headers, json=payload)

    assert created.status_code == 201
    assert duplicate.status_code == 409


async def test_update_rejects_null_for_name_and_is_active(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))
    project = await make_project()

    for field in ("name", "is_active"):
        response = await client.patch(
            f"/api/v1/projects/{project.id}", headers=headers, json={field: None}
        )
        assert response.status_code == 422


async def test_add_member_with_inactive_user_returns_400_and_duplicate_returns_409(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))
    project = await make_project()
    inactive_user = await make_user()
    await client.patch(
        f"/api/v1/users/{inactive_user.id}", headers=headers, json={"is_active": False}
    )

    rejected = await client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=headers,
        json={"user_id": str(inactive_user.id)},
    )
    assert rejected.status_code == 400

    active_user = await make_user()
    added = await client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=headers,
        json={"user_id": str(active_user.id)},
    )
    duplicate = await client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=headers,
        json={"user_id": str(active_user.id)},
    )
    assert added.status_code == 201
    assert duplicate.status_code == 409


async def test_member_id_filter_returns_only_that_members_projects(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))
    member = await make_user()
    project_with_member = await make_project()
    await make_project()
    await client.post(
        f"/api/v1/projects/{project_with_member.id}/members",
        headers=headers,
        json={"user_id": str(member.id)},
    )

    response = await client.get(
        "/api/v1/projects", headers=headers, params={"member_id": str(member.id)}
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {str(project_with_member.id)}
