from uuid import uuid4

import pytest
from httpx import AsyncClient

from support import DEFAULT_PASSWORD, AuthHeaders, CustomerFactory, ProjectFactory, UserFactory
from time_reporting.modules.auth.session_cookie import CSRF_HEADER
from time_reporting.modules.projects.contracts import BillingItemPreset
from time_reporting.modules.users.contracts import UserRole

CSRF_HEADERS = {CSRF_HEADER: "fetch"}
# 2026-09-14 is a Monday.
A_MONDAY = "2026-09-14"


async def _book_normal_hours(
    client: AsyncClient, headers: dict[str, str], *, project_id: str
) -> None:
    """Book one hour of normal working time on ``project_id`` for the caller identified by
    ``headers``, so a permanent delete of them/the project is blocked by a real time entry."""
    items = await client.get(f"/api/v1/projects/{project_id}/billing-items", headers=headers)
    item_id = next(
        i["id"] for i in items.json() if i["preset"] == BillingItemPreset.NORMAL_HOURS.value
    )
    response = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "1.00"}]},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("role", [UserRole.PROJECT_MANAGER, UserRole.WORKER])
async def test_non_admin_cannot_use_admin_routes(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
    role: UserRole,
) -> None:
    headers = auth_headers(await make_user(role=role))
    other_user = await make_user()
    customer = await make_customer()
    project = await make_project()

    responses = [
        await client.get(f"/api/v1/admin/users/{other_user.id}/removal-impact", headers=headers),
        await client.delete(f"/api/v1/admin/users/{other_user.id}", headers=headers),
        await client.get(f"/api/v1/admin/customers/{customer.id}/removal-impact", headers=headers),
        await client.delete(f"/api/v1/admin/customers/{customer.id}", headers=headers),
        await client.get(f"/api/v1/admin/projects/{project.id}/removal-impact", headers=headers),
        await client.delete(f"/api/v1/admin/projects/{project.id}", headers=headers),
    ]

    assert {r.status_code for r in responses} == {403}


async def test_anonymous_cannot_use_admin_routes(
    client: AsyncClient, make_user: UserFactory
) -> None:
    user = await make_user()

    response = await client.delete(f"/api/v1/admin/users/{user.id}")

    assert response.status_code == 401


async def test_admin_can_archive_and_then_permanently_delete_a_customer(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))
    customer = await make_customer()

    impact = await client.get(
        f"/api/v1/admin/customers/{customer.id}/removal-impact", headers=headers
    )
    assert impact.status_code == 200
    assert impact.json() == {
        "is_active": True,
        "can_delete_permanently": True,
        "blockers": [],
        "effects": [],
    }

    archived = await client.delete(f"/api/v1/admin/customers/{customer.id}", headers=headers)
    assert archived.status_code == 200
    assert archived.json() == {"outcome": "archived"}
    assert (await client.get(f"/api/v1/customers/{customer.id}", headers=headers)).json()[
        "is_active"
    ] is False

    deleted = await client.delete(
        f"/api/v1/admin/customers/{customer.id}",
        headers=headers,
        params={"permanent": "true"},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"outcome": "deleted"}
    assert (
        await client.get(f"/api/v1/customers/{customer.id}", headers=headers)
    ).status_code == 404


async def test_permanent_delete_blocked_by_project_returns_409_with_blockers(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))
    customer = await make_customer()
    await make_project(customer_id=customer.id)

    response = await client.delete(
        f"/api/v1/admin/customers/{customer.id}",
        headers=headers,
        params={"permanent": "true"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["blockers"] == [{"kind": "projects", "count": 1}]


async def test_permanent_delete_blocked_by_time_entries_returns_409(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin_headers = auth_headers(await make_user(role=UserRole.ADMIN))
    worker = await make_user(role=UserRole.WORKER)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=admin_headers,
        json={"user_id": str(worker.id)},
    )
    await _book_normal_hours(client, worker_headers, project_id=str(project.id))

    user_response = await client.delete(
        f"/api/v1/admin/users/{worker.id}", headers=admin_headers, params={"permanent": "true"}
    )
    project_response = await client.delete(
        f"/api/v1/admin/projects/{project.id}",
        headers=admin_headers,
        params={"permanent": "true"},
    )

    assert user_response.status_code == 409
    assert user_response.json()["detail"]["blockers"] == [{"kind": "time_entries", "count": 1}]
    assert project_response.status_code == 409
    assert project_response.json()["detail"]["blockers"] == [{"kind": "time_entries", "count": 1}]


async def test_admin_cannot_remove_self(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    headers = auth_headers(admin)

    response = await client.delete(f"/api/v1/admin/users/{admin.id}", headers=headers)

    assert response.status_code == 400


async def test_remove_unknown_record_returns_404(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(role=UserRole.ADMIN))

    response = await client.delete(f"/api/v1/admin/customers/{uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_permanently_deleting_a_user_removes_project_membership(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    headers = auth_headers(admin)
    user = await make_user()
    project = await make_project()
    await client.post(
        f"/api/v1/projects/{project.id}/members", headers=headers, json={"user_id": str(user.id)}
    )

    response = await client.delete(
        f"/api/v1/admin/users/{user.id}", headers=headers, params={"permanent": "true"}
    )

    assert response.status_code == 200
    assert response.json() == {"outcome": "deleted"}
    members = await client.get(f"/api/v1/projects/{project.id}/members", headers=headers)
    assert members.json() == []


async def test_cookie_authenticated_delete_requires_csrf_header(
    client: AsyncClient, make_user: UserFactory
) -> None:
    admin_email = "admin-csrf@example.com"
    await make_user(role=UserRole.ADMIN, email=admin_email)

    sign_in = await client.post(
        "/api/v1/auth/session", json={"email": admin_email, "password": DEFAULT_PASSWORD}
    )
    assert sign_in.status_code == 200
    target = await make_user()

    without_header = await client.delete(f"/api/v1/admin/users/{target.id}")
    with_header = await client.delete(f"/api/v1/admin/users/{target.id}", headers=CSRF_HEADERS)

    assert without_header.status_code == 403
    assert with_header.status_code == 200
