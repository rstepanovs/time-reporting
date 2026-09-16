"""HTTP API for `GET /admin/audit-events`: admin gating, filters and pagination end to end."""

import pytest
from httpx import AsyncClient

from support import ADMIN, EMPLOYEE, MANAGER, AuthHeaders, UserFactory
from time_reporting.modules.users.contracts import UserRole


async def test_anonymous_cannot_list_audit_events(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/audit-events")

    assert response.status_code == 401


@pytest.mark.parametrize("roles", [MANAGER, EMPLOYEE])
async def test_non_admin_cannot_list_audit_events(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    response = await client.get("/api/v1/admin/audit-events", headers=headers)

    assert response.status_code == 403


async def test_admin_can_list_and_filter_audit_events(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin = await make_user(roles=ADMIN)
    headers = auth_headers(admin)

    # `make_user` itself already recorded a `user.created` event for `admin`.
    everything = await client.get("/api/v1/admin/audit-events", headers=headers)
    assert everything.status_code == 200
    assert everything.json()["total"] >= 1

    by_entity = await client.get(
        "/api/v1/admin/audit-events",
        headers=headers,
        params={"action": "user.created", "entity_type": "user", "entity_id": str(admin.id)},
    )
    assert by_entity.status_code == 200
    body = by_entity.json()
    assert body["total"] == 1
    event = body["items"][0]
    assert event["action"] == "user.created"
    assert event["entity_type"] == "user"
    assert event["entity_id"] == str(admin.id)
    assert admin.name in event["summary"]

    paged = await client.get(
        "/api/v1/admin/audit-events", headers=headers, params={"limit": 1, "offset": 0}
    )
    assert paged.status_code == 200
    assert len(paged.json()["items"]) == 1
    assert paged.json()["limit"] == 1
