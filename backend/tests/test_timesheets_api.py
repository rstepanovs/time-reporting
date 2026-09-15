from datetime import date

import pytest
from httpx import AsyncClient

from support import AuthHeaders, ProjectFactory, UserFactory
from time_reporting.modules.projects.contracts import BillingItemPreset
from time_reporting.modules.users.contracts import UserRole

# 2026-09-14 is a Monday.
A_MONDAY = "2026-09-14"
A_TUESDAY = "2026-09-15"


async def _add_member(
    client: AsyncClient, headers: dict[str, str], project_id: str, user_id: str
) -> None:
    response = await client.post(
        f"/api/v1/projects/{project_id}/members", headers=headers, json={"user_id": user_id}
    )
    assert response.status_code == 201


async def _normal_hours_item_id(
    client: AsyncClient, headers: dict[str, str], project_id: str
) -> str:
    response = await client.get(f"/api/v1/projects/{project_id}/billing-items", headers=headers)
    item = next(i for i in response.json() if i["preset"] == BillingItemPreset.NORMAL_HOURS.value)
    return str(item["id"])


async def test_worker_can_read_and_write_their_own_week(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin = await make_user(role=UserRole.ADMIN)
    admin_headers = auth_headers(admin)
    worker = await make_user(role=UserRole.WORKER)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, admin_headers, str(project.id))

    empty_week = await client.get(f"/api/v1/timesheets/weeks/{A_MONDAY}", headers=worker_headers)
    assert empty_week.status_code == 200
    assert empty_week.json()["can_edit"] is True
    assert empty_week.json()["rows"] == []

    saved = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "8.00"}]},
    )
    assert saved.status_code == 200
    row = next(r for r in saved.json()["rows"] if r["billing_item"]["id"] == item_id)
    assert row["entries"] == [{"date": A_MONDAY, "quantity": "8.00", "note": None}]
    assert row["is_open"] is True

    cleared = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": None}]},
    )
    assert cleared.status_code == 200
    assert cleared.json()["rows"] == []


async def test_worker_cannot_view_or_edit_someone_elses_week(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    worker = await make_user(role=UserRole.WORKER)
    other = await make_user(role=UserRole.WORKER)
    headers = auth_headers(worker)

    response = await client.get(
        f"/api/v1/timesheets/weeks/{A_MONDAY}",
        headers=headers,
        params={"user_id": str(other.id)},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.PROJECT_MANAGER])
async def test_manager_can_view_but_not_edit_someone_elses_week(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
    role: UserRole,
) -> None:
    manager = await make_user(role=role)
    manager_headers = auth_headers(manager)
    worker = await make_user(role=UserRole.WORKER)
    project = await make_project()
    await _add_member(client, manager_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, manager_headers, str(project.id))

    await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=auth_headers(worker),
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "4.00"}]},
    )

    viewed = await client.get(
        f"/api/v1/timesheets/weeks/{A_MONDAY}",
        headers=manager_headers,
        params={"user_id": str(worker.id)},
    )

    assert viewed.status_code == 200
    assert viewed.json()["can_edit"] is False
    assert viewed.json()["user"]["id"] == str(worker.id)


async def test_get_week_rejects_non_monday(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user())

    response = await client.get(f"/api/v1/timesheets/weeks/{A_TUESDAY}", headers=headers)

    assert response.status_code == 400


async def test_save_week_reports_rule_violations_with_detail(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin_headers = auth_headers(await make_user(role=UserRole.ADMIN))
    worker = await make_user(role=UserRole.WORKER)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, admin_headers, str(project.id))

    response = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "30.00"}]},
    )

    assert response.status_code == 400
    assert "out of range" in response.json()["detail"]


async def test_save_week_rejects_unknown_billing_item_with_404(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(role=UserRole.WORKER))

    response = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=headers,
        json={
            "changes": [
                {
                    "billing_item_id": "00000000-0000-0000-0000-000000000000",
                    "date": A_MONDAY,
                    "quantity": "1.00",
                }
            ]
        },
    )

    assert response.status_code == 404


async def test_timesheets_require_authentication(client: AsyncClient) -> None:
    week = await client.get(f"/api/v1/timesheets/weeks/{A_MONDAY}")
    options = await client.get("/api/v1/timesheets/options")

    assert week.status_code == 401
    assert options.status_code == 401


async def test_list_timesheet_options_returns_member_projects(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin_headers = auth_headers(await make_user(role=UserRole.ADMIN))
    worker = await make_user(role=UserRole.WORKER)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))

    response = await client.get("/api/v1/timesheets/options", headers=worker_headers)

    assert response.status_code == 200
    body = response.json()
    assert [option["project"]["id"] for option in body] == [str(project.id)]
    assert len(body[0]["billing_items"]) == 6


async def test_worker_can_read_own_month_calendar_and_year_hours(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    worker = await make_user(role=UserRole.WORKER)
    headers = auth_headers(worker)

    calendar = await client.get(
        "/api/v1/timesheets/calendar", headers=headers, params={"year": 2026, "month": 9}
    )
    year = await client.get("/api/v1/timesheets/years/2026", headers=headers)

    assert calendar.status_code == 200
    assert calendar.json()["user"]["id"] == str(worker.id)
    assert calendar.json()["year"] == 2026
    assert calendar.json()["month"] == 9
    assert year.status_code == 200
    assert year.json()["user"]["id"] == str(worker.id)
    assert year.json()["year"] == 2026


async def test_worker_cannot_view_someone_elses_calendar_or_year_hours(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    worker = await make_user(role=UserRole.WORKER)
    other = await make_user(role=UserRole.WORKER)
    headers = auth_headers(worker)

    calendar = await client.get(
        "/api/v1/timesheets/calendar",
        headers=headers,
        params={"year": 2026, "month": 9, "user_id": str(other.id)},
    )
    year = await client.get(
        "/api/v1/timesheets/years/2026", headers=headers, params={"user_id": str(other.id)}
    )

    assert calendar.status_code == 403
    assert year.status_code == 403


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.PROJECT_MANAGER])
async def test_manager_can_view_someone_elses_calendar_and_year_hours(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders, role: UserRole
) -> None:
    manager_headers = auth_headers(await make_user(role=role))
    worker = await make_user(role=UserRole.WORKER)

    calendar = await client.get(
        "/api/v1/timesheets/calendar",
        headers=manager_headers,
        params={"year": 2026, "month": 9, "user_id": str(worker.id)},
    )
    year = await client.get(
        "/api/v1/timesheets/years/2026",
        headers=manager_headers,
        params={"user_id": str(worker.id)},
    )

    assert calendar.status_code == 200
    assert calendar.json()["user"]["id"] == str(worker.id)
    assert year.status_code == 200
    assert year.json()["user"]["id"] == str(worker.id)


async def test_calendar_and_year_hours_default_to_today(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(role=UserRole.WORKER))

    calendar = await client.get("/api/v1/timesheets/calendar", headers=headers)

    assert calendar.status_code == 200
    today = date.today()
    assert calendar.json()["year"] == today.year
    assert calendar.json()["month"] == today.month


async def test_calendar_and_year_hours_for_unknown_user_return_404(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin_headers = auth_headers(await make_user(role=UserRole.ADMIN))
    unknown_user_id = "00000000-0000-0000-0000-000000000000"

    calendar = await client.get(
        "/api/v1/timesheets/calendar",
        headers=admin_headers,
        params={"year": 2026, "month": 9, "user_id": unknown_user_id},
    )
    year = await client.get(
        "/api/v1/timesheets/years/2026",
        headers=admin_headers,
        params={"user_id": unknown_user_id},
    )

    assert calendar.status_code == 404
    assert year.status_code == 404


async def test_calendar_and_year_hours_reject_out_of_range_query_params(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(role=UserRole.WORKER))

    bad_month = await client.get(
        "/api/v1/timesheets/calendar", headers=headers, params={"year": 2026, "month": 13}
    )
    bad_year = await client.get("/api/v1/timesheets/years/1999", headers=headers)

    assert bad_month.status_code == 422
    assert bad_year.status_code == 422


async def test_calendar_and_year_hours_require_authentication(client: AsyncClient) -> None:
    calendar = await client.get("/api/v1/timesheets/calendar")
    year = await client.get("/api/v1/timesheets/years/2026")

    assert calendar.status_code == 401
    assert year.status_code == 401
