from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from support import (
    ADMIN,
    EMPLOYEE,
    MANAGER,
    AuthHeaders,
    CustomerFactory,
    ProjectFactory,
    UserFactory,
)
from time_reporting.modules.users.contracts import UserRole


@pytest.mark.parametrize("roles", [ADMIN, MANAGER])
async def test_manager_full_project_lifecycle(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))
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
    assert body["normal_working_hours"] == "8.00"
    project_id = body["id"]

    patched = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=headers,
        json={"description": "Redesign the marketing site", "normal_working_hours": "6.50"},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Redesign the marketing site"
    assert patched.json()["name"] == "Website Revamp"
    assert patched.json()["normal_working_hours"] == "6.50"

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
    headers = auth_headers(await make_user(roles=EMPLOYEE))
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
    headers = auth_headers(await make_user(roles=ADMIN))
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
    headers = auth_headers(await make_user(roles=ADMIN))

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
    headers = auth_headers(await make_user(roles=ADMIN))
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
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()

    for field in ("name", "is_active", "normal_working_hours"):
        response = await client.patch(
            f"/api/v1/projects/{project.id}", headers=headers, json={field: None}
        )
        assert response.status_code == 422


@pytest.mark.parametrize("normal_working_hours", ["0", "-1", "24.01"])
async def test_normal_working_hours_out_of_range_returns_422(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
    normal_working_hours: str,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    customer = await make_customer()

    response = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "customer_id": str(customer.id),
            "name": "Out Of Range",
            "normal_working_hours": normal_working_hours,
        },
    )

    assert response.status_code == 422


async def test_add_member_with_inactive_user_returns_400_and_duplicate_returns_409(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
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
    headers = auth_headers(await make_user(roles=ADMIN))
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


# --- Project manager ---


async def test_create_and_update_project_manager(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    customer = await make_customer()
    manager = await make_user(roles=MANAGER, name="Mark Manager")

    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"customer_id": str(customer.id), "name": "Managed", "manager_id": str(manager.id)},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["manager"]["id"] == str(manager.id)
    assert body["manager"]["name"] == "Mark Manager"
    project_id = body["id"]

    cleared = await client.patch(
        f"/api/v1/projects/{project_id}", headers=headers, json={"manager_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["manager"] is None


async def test_create_project_with_worker_as_manager_returns_400(
    client: AsyncClient,
    make_user: UserFactory,
    make_customer: CustomerFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    customer = await make_customer()
    worker = await make_user(roles=EMPLOYEE)

    response = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"customer_id": str(customer.id), "name": "X", "manager_id": str(worker.id)},
    )

    assert response.status_code == 400


async def test_manager_id_filter_returns_only_that_managers_projects(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    manager = await make_user(roles=MANAGER)
    managed = await make_project(manager_id=manager.id)
    await make_project()

    response = await client.get(
        "/api/v1/projects", headers=headers, params={"manager_id": str(manager.id)}
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {str(managed.id)}


# --- Billing items ---


async def test_list_billing_items_returns_the_six_defaults(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=EMPLOYEE))
    project = await make_project()

    response = await client.get(f"/api/v1/projects/{project.id}/billing-items", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6
    assert body[0]["name"] == "Normal working hours"
    assert body[0]["preset"] == "normal_hours"
    assert body[0]["unit"] == "hour"
    assert body[0]["unit_rate"] is None
    assert body[0]["is_active"] is True


@pytest.mark.parametrize("roles", [ADMIN, MANAGER])
async def test_manager_can_add_and_update_a_billing_item(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))
    project = await make_project()

    created = await client.post(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=headers,
        json={
            "name": "On-call standby",
            "unit": "hour",
            "description": "Weekend on-call",
            "unit_rate": "50.00",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["preset"] is None
    assert body["position"] == 7
    # Decimals round-trip as JSON strings, not floats, so the rate isn't rounded in transit.
    assert body["unit_rate"] == "50.00"
    assert isinstance(body["unit_rate"], str)
    item_id = body["id"]

    patched = await client.patch(
        f"/api/v1/projects/{project.id}/billing-items/{item_id}",
        headers=headers,
        json={"name": "On-call", "unit_rate": "60.00"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "On-call"
    assert patched.json()["unit_rate"] == "60.00"
    assert patched.json()["unit"] == "hour"


async def test_worker_can_read_but_not_write_billing_items(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=EMPLOYEE))
    project = await make_project()
    url = f"/api/v1/projects/{project.id}/billing-items"

    listed = await client.get(url, headers=headers)
    created = await client.post(url, headers=headers, json={"name": "Extra", "unit": "hour"})
    patched = await client.patch(f"{url}/{uuid4()}", headers=headers, json={"name": "X"})
    deleted = await client.delete(f"{url}/{uuid4()}", headers=headers)

    assert listed.status_code == 200
    assert created.status_code == 403
    assert patched.status_code == 403
    assert deleted.status_code == 403


async def test_project_manager_cannot_permanently_delete_a_billing_item(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    manager_headers = auth_headers(await make_user(roles=MANAGER))
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    created = await client.post(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=admin_headers,
        json={"name": "Extra", "unit": "hour"},
    )
    item_id = created.json()["id"]
    url = f"/api/v1/projects/{project.id}/billing-items/{item_id}"

    forbidden = await client.delete(url, headers=manager_headers)
    assert forbidden.status_code == 403

    allowed = await client.delete(url, headers=admin_headers)
    assert allowed.status_code == 204


async def test_admin_cannot_permanently_delete_a_billing_item_in_use(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=admin_headers,
        json={"user_id": str(worker.id)},
    )
    items = await client.get(f"/api/v1/projects/{project.id}/billing-items", headers=admin_headers)
    item_id = next(i["id"] for i in items.json() if i["preset"] == "normal_hours")
    # 2026-09-14 is a Monday.
    booked = await client.put(
        "/api/v1/timesheets/weeks/2026-09-14/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": "2026-09-14", "quantity": "1.00"}]},
    )
    assert booked.status_code == 200

    response = await client.delete(
        f"/api/v1/projects/{project.id}/billing-items/{item_id}", headers=admin_headers
    )

    assert response.status_code == 409


async def test_billing_items_require_authentication(
    client: AsyncClient, make_project: ProjectFactory
) -> None:
    project = await make_project()
    url = f"/api/v1/projects/{project.id}/billing-items"

    assert (await client.get(url)).status_code == 401
    assert (await client.post(url, json={"name": "Extra", "unit": "hour"})).status_code == 401


async def test_unknown_project_returns_404_for_billing_item_routes(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    url = f"/api/v1/projects/{uuid4()}/billing-items"

    assert (await client.get(url, headers=headers)).status_code == 404
    assert (
        await client.post(url, headers=headers, json={"name": "Extra", "unit": "hour"})
    ).status_code == 404
    assert (
        await client.patch(f"{url}/{uuid4()}", headers=headers, json={"name": "X"})
    ).status_code == 404
    assert (await client.delete(f"{url}/{uuid4()}", headers=headers)).status_code == 404


async def test_unknown_billing_item_for_a_real_project_returns_404(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    url = f"/api/v1/projects/{project.id}/billing-items/{uuid4()}"

    assert (await client.patch(url, headers=headers, json={"name": "X"})).status_code == 404
    assert (await client.delete(url, headers=headers)).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Expense", "unit": "amount", "unit_rate": "10.00"},
        {"name": "Hours", "unit": "hour", "markup_percent": "10.00"},
    ],
)
async def test_add_billing_item_with_pricing_for_the_wrong_unit_returns_400(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
    payload: dict[str, Any],
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()

    response = await client.post(
        f"/api/v1/projects/{project.id}/billing-items", headers=headers, json=payload
    )

    assert response.status_code == 400


async def test_add_billing_item_to_archived_project_returns_400(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await client.patch(f"/api/v1/projects/{project.id}", headers=headers, json={"is_active": False})

    response = await client.post(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=headers,
        json={"name": "Extra", "unit": "hour"},
    )

    assert response.status_code == 400


async def test_duplicate_billing_item_name_returns_409(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    payload = {"name": "Normal working hours", "unit": "hour"}

    response = await client.post(
        f"/api/v1/projects/{project.id}/billing-items", headers=headers, json=payload
    )

    assert response.status_code == 409


async def test_update_billing_item_rejects_null_for_name_and_is_active(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    created = await client.post(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=headers,
        json={"name": "Extra", "unit": "hour"},
    )
    item_id = created.json()["id"]

    for field in ("name", "is_active"):
        response = await client.patch(
            f"/api/v1/projects/{project.id}/billing-items/{item_id}",
            headers=headers,
            json={field: None},
        )
        assert response.status_code == 422


async def test_update_rejects_unit_and_preset(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    created = await client.post(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=headers,
        json={"name": "Extra", "unit": "hour"},
    )
    item_id = created.json()["id"]

    for field, value in (("unit", "day"), ("preset", "per_diem")):
        response = await client.patch(
            f"/api/v1/projects/{project.id}/billing-items/{item_id}",
            headers=headers,
            json={field: value},
        )
        assert response.status_code == 422


async def test_update_clears_description_and_unit_rate(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    created = await client.post(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=headers,
        json={"name": "Extra", "unit": "hour", "description": "Notes", "unit_rate": "50.00"},
    )
    item_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/projects/{project.id}/billing-items/{item_id}",
        headers=headers,
        json={"description": None, "unit_rate": None},
    )

    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["unit_rate"] is None


async def test_include_inactive_query_param(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    created = await client.post(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=headers,
        json={"name": "Extra", "unit": "hour"},
    )
    item_id = created.json()["id"]
    await client.patch(
        f"/api/v1/projects/{project.id}/billing-items/{item_id}",
        headers=headers,
        json={"is_active": False},
    )

    default_listing = await client.get(
        f"/api/v1/projects/{project.id}/billing-items", headers=headers
    )
    assert "Extra" not in {i["name"] for i in default_listing.json()}

    full_listing = await client.get(
        f"/api/v1/projects/{project.id}/billing-items",
        headers=headers,
        params={"include_inactive": True},
    )
    assert "Extra" in {i["name"] for i in full_listing.json()}


async def test_project_customer_response_includes_currency(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    headers = auth_headers(await make_user(roles=EMPLOYEE))
    project = await make_project()

    response = await client.get(f"/api/v1/projects/{project.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["customer"]["currency"]
