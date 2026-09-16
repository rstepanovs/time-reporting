import pytest
from httpx import AsyncClient

from support import ADMIN, EMPLOYEE, MANAGER, AuthHeaders, UserFactory
from time_reporting.modules.users.contracts import UserRole


async def test_admin_can_manage_non_working_days(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    created = await client.post(
        "/api/v1/calendar/non-working-days",
        headers=headers,
        json={"day": "2026-12-24", "name": "Christmas Eve", "kind": "company_day_off"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["kind"] == "company_day_off"

    updated = await client.patch(
        f"/api/v1/calendar/non-working-days/{body['id']}",
        headers=headers,
        json={"name": "Christmas Eve (half day)"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Christmas Eve (half day)"

    listed = await client.get(
        "/api/v1/calendar/non-working-days", headers=headers, params={"year": 2026}
    )
    assert listed.status_code == 200
    assert body["id"] in {item["id"] for item in listed.json()}

    deleted = await client.delete(
        f"/api/v1/calendar/non-working-days/{body['id']}", headers=headers
    )
    assert deleted.status_code == 204

    after_delete = await client.get(
        "/api/v1/calendar/non-working-days", headers=headers, params={"year": 2026}
    )
    assert body["id"] not in {item["id"] for item in after_delete.json()}


async def test_creating_a_duplicate_date_conflicts(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    payload = {"day": "2026-01-01", "name": "New Year", "kind": "public_holiday"}

    first = await client.post("/api/v1/calendar/non-working-days", headers=headers, json=payload)
    second = await client.post("/api/v1/calendar/non-working-days", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


async def test_updating_or_deleting_unknown_day_is_not_found(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    missing_id = "00000000-0000-0000-0000-000000000000"

    updated = await client.patch(
        f"/api/v1/calendar/non-working-days/{missing_id}", headers=headers, json={"name": "Nobody"}
    )
    deleted = await client.delete(
        f"/api/v1/calendar/non-working-days/{missing_id}", headers=headers
    )

    assert updated.status_code == 404
    assert deleted.status_code == 404


@pytest.mark.parametrize("roles", [EMPLOYEE, MANAGER])
async def test_non_admins_read_but_get_403_on_writes(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))

    listed = await client.get("/api/v1/calendar/non-working-days", headers=headers)
    days = await client.get(
        "/api/v1/calendar/days",
        headers=headers,
        params={"from": "2026-09-14", "to": "2026-09-20"},
    )
    created = await client.post(
        "/api/v1/calendar/non-working-days",
        headers=headers,
        json={"day": "2026-12-24", "name": "Christmas Eve", "kind": "company_day_off"},
    )
    imported = await client.post(
        "/api/v1/calendar/non-working-days/import", headers=headers, json={"year": 2026}
    )

    assert listed.status_code == 200
    assert days.status_code == 200
    assert created.status_code == 403
    assert imported.status_code == 403


async def test_get_calendar_days_marks_weekends_and_holidays(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))
    await client.post(
        "/api/v1/calendar/non-working-days",
        headers=headers,
        json={"day": "2026-09-16", "name": "Custom Holiday", "kind": "company_day_off"},
    )

    response = await client.get(
        "/api/v1/calendar/days",
        headers=headers,
        params={"from": "2026-09-14", "to": "2026-09-20"},
    )

    assert response.status_code == 200
    by_date = {item["day"]: item for item in response.json()}
    assert by_date["2026-09-14"]["is_weekend"] is False
    assert by_date["2026-09-19"]["is_weekend"] is True
    assert by_date["2026-09-16"]["non_working_day"]["name"] == "Custom Holiday"
    assert by_date["2026-09-14"]["non_working_day"] is None


async def test_get_calendar_days_rejects_too_wide_a_range(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=EMPLOYEE))

    response = await client.get(
        "/api/v1/calendar/days",
        headers=headers,
        params={"from": "2020-01-01", "to": "2026-01-01"},
    )

    assert response.status_code == 400


async def test_admin_can_import_public_holidays(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=ADMIN))

    first = await client.post(
        "/api/v1/calendar/non-working-days/import", headers=headers, json={"year": 2026}
    )
    second = await client.post(
        "/api/v1/calendar/non-working-days/import", headers=headers, json={"year": 2026}
    )

    assert first.status_code == 200
    assert first.json()["added"] > 0
    assert second.status_code == 200
    assert second.json()["added"] == 0

    listed = await client.get(
        "/api/v1/calendar/non-working-days", headers=headers, params={"year": 2026}
    )
    names = {item["name"] for item in listed.json()}
    assert "New Year's Day" in names
