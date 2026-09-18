import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from support import ADMIN, ADMIN_ONLY, EMPLOYEE, MANAGER, AuthHeaders, ProjectFactory, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.expenses.contracts import (
    ApproveExpenseReport,
    CreateExpenseReport,
    ExpenseLineChange,
    SaveExpenseReportLines,
    SubmitExpenseReport,
)
from time_reporting.modules.projects.contracts import BillingItemPreset, ListProjectBillingItems
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
    admin = await make_user(roles=ADMIN)
    admin_headers = auth_headers(admin)
    worker = await make_user(roles=EMPLOYEE)
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
    worker = await make_user(roles=EMPLOYEE)
    other = await make_user(roles=EMPLOYEE)
    headers = auth_headers(worker)

    response = await client.get(
        f"/api/v1/timesheets/weeks/{A_MONDAY}",
        headers=headers,
        params={"user_id": str(other.id)},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("roles", [ADMIN, MANAGER])
async def test_manager_can_view_but_not_edit_someone_elses_week(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    manager = await make_user(roles=roles)
    manager_headers = auth_headers(manager)
    worker = await make_user(roles=EMPLOYEE)
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
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    worker = await make_user(roles=EMPLOYEE)
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
    headers = auth_headers(await make_user(roles=EMPLOYEE))

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
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))

    response = await client.get("/api/v1/timesheets/options", headers=worker_headers)

    assert response.status_code == 200
    body = response.json()
    assert [option["project"]["id"] for option in body] == [str(project.id)]
    # 6 defaults minus the 2 `amount` ones, claimed through the expenses module now.
    assert len(body[0]["billing_items"]) == 4
    assert all(item["unit"] != "amount" for item in body[0]["billing_items"])


async def test_worker_can_read_own_month_calendar_and_year_hours(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    worker = await make_user(roles=EMPLOYEE)
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
    worker = await make_user(roles=EMPLOYEE)
    other = await make_user(roles=EMPLOYEE)
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


@pytest.mark.parametrize("roles", [ADMIN, MANAGER])
async def test_manager_can_view_someone_elses_calendar_and_year_hours(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    manager_headers = auth_headers(await make_user(roles=roles))
    worker = await make_user(roles=EMPLOYEE)

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
    headers = auth_headers(await make_user(roles=EMPLOYEE))

    calendar = await client.get("/api/v1/timesheets/calendar", headers=headers)

    assert calendar.status_code == 200
    today = date.today()
    assert calendar.json()["year"] == today.year
    assert calendar.json()["month"] == today.month


async def test_calendar_and_year_hours_for_unknown_user_return_404(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin_headers = auth_headers(await make_user(roles=ADMIN))
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
    headers = auth_headers(await make_user(roles=EMPLOYEE))

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


async def test_worker_can_read_own_month_summary_and_weekly_hours(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    headers = auth_headers(worker)

    summary = await client.get("/api/v1/timesheets/months/2026/9/summary", headers=headers)
    weekly = await client.get(
        "/api/v1/timesheets/weekly-hours", headers=headers, params={"weeks": 4}
    )

    assert summary.status_code == 200
    assert summary.json()["user"]["id"] == str(worker.id)
    assert summary.json()["year"] == 2026
    assert summary.json()["month"] == 9
    assert weekly.status_code == 200
    assert weekly.json()["user"]["id"] == str(worker.id)
    assert len(weekly.json()["weeks"]) == 4


async def test_worker_cannot_view_someone_elses_month_summary_or_weekly_hours(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    other = await make_user(roles=EMPLOYEE)
    headers = auth_headers(worker)

    summary = await client.get(
        "/api/v1/timesheets/months/2026/9/summary",
        headers=headers,
        params={"user_id": str(other.id)},
    )
    weekly = await client.get(
        "/api/v1/timesheets/weekly-hours", headers=headers, params={"user_id": str(other.id)}
    )

    assert summary.status_code == 403
    assert weekly.status_code == 403


@pytest.mark.parametrize("roles", [ADMIN, MANAGER])
async def test_manager_can_view_someone_elses_month_summary_and_weekly_hours(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    manager_headers = auth_headers(await make_user(roles=roles))
    worker = await make_user(roles=EMPLOYEE)

    summary = await client.get(
        "/api/v1/timesheets/months/2026/9/summary",
        headers=manager_headers,
        params={"user_id": str(worker.id)},
    )
    weekly = await client.get(
        "/api/v1/timesheets/weekly-hours",
        headers=manager_headers,
        params={"user_id": str(worker.id)},
    )

    assert summary.status_code == 200
    assert summary.json()["user"]["id"] == str(worker.id)
    assert weekly.status_code == 200
    assert weekly.json()["user"]["id"] == str(worker.id)


async def test_weekly_hours_defaults_to_six_weeks(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=EMPLOYEE))

    weekly = await client.get("/api/v1/timesheets/weekly-hours", headers=headers)

    assert weekly.status_code == 200
    assert len(weekly.json()["weeks"]) == 6


async def test_month_summary_and_weekly_hours_for_unknown_user_return_404(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    unknown_user_id = "00000000-0000-0000-0000-000000000000"

    summary = await client.get(
        "/api/v1/timesheets/months/2026/9/summary",
        headers=admin_headers,
        params={"user_id": unknown_user_id},
    )
    weekly = await client.get(
        "/api/v1/timesheets/weekly-hours",
        headers=admin_headers,
        params={"user_id": unknown_user_id},
    )

    assert summary.status_code == 404
    assert weekly.status_code == 404


async def test_month_summary_and_weekly_hours_reject_out_of_range_query_params(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    headers = auth_headers(await make_user(roles=EMPLOYEE))

    bad_month = await client.get("/api/v1/timesheets/months/2026/13/summary", headers=headers)
    bad_weeks = await client.get(
        "/api/v1/timesheets/weekly-hours", headers=headers, params={"weeks": 27}
    )

    assert bad_month.status_code == 422
    assert bad_weeks.status_code == 422


async def test_month_summary_and_weekly_hours_require_authentication(
    client: AsyncClient,
) -> None:
    summary = await client.get("/api/v1/timesheets/months/2026/9/summary")
    weekly = await client.get("/api/v1/timesheets/weekly-hours")

    assert summary.status_code == 401
    assert weekly.status_code == 401


# --- Row comments ---


async def test_save_week_creates_and_clears_a_row_comment(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, admin_headers, str(project.id))

    saved = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={
            "changes": [],
            "row_comments": [{"billing_item_id": item_id, "comment": "Please review"}],
        },
    )
    assert saved.status_code == 200
    row = next(r for r in saved.json()["rows"] if r["billing_item"]["id"] == item_id)
    assert row["comment"] == "Please review"
    assert row["entries"] == []

    cleared = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [], "row_comments": [{"billing_item_id": item_id, "comment": None}]},
    )
    assert cleared.status_code == 200
    assert cleared.json()["rows"] == []


# --- Submit / approve / return workflow ---


async def _setup_worker_with_hours(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> tuple[dict[str, str], dict[str, str]]:
    """A worker with 8 booked hours in ``A_MONDAY``'s week, plus a project manager's headers."""
    manager = await make_user(roles=MANAGER)
    manager_headers = auth_headers(manager)
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project()
    await _add_member(client, manager_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, manager_headers, str(project.id))
    await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "8.00"}]},
    )
    return worker_headers, manager_headers


async def test_worker_can_submit_and_manager_can_approve(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker_headers, manager_headers = await _setup_worker_with_hours(
        client, make_user, make_project, auth_headers
    )
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]

    submitted = await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    locked = await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": []},
    )
    assert locked.status_code == 409

    approved = await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/approve",
        headers=manager_headers,
        params={"user_id": worker_id},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


async def test_manager_can_return_a_week_with_a_comment(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker_headers, manager_headers = await _setup_worker_with_hours(
        client, make_user, make_project, auth_headers
    )
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)

    # A whitespace-only comment is stripped to empty by the schema's `min_length=1`, so this is
    # rejected at the HTTP boundary (422) before ever reaching the domain-level check.
    missing_comment = await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/return",
        headers=manager_headers,
        params={"user_id": worker_id},
        json={"comment": "   "},
    )
    assert missing_comment.status_code == 422

    returned = await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/return",
        headers=manager_headers,
        params={"user_id": worker_id},
        json={"comment": "Please add the missing hours"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"
    assert returned.json()["return_comment"] == "Please add the missing hours"

    reread = await client.get(f"/api/v1/timesheets/weeks/{A_MONDAY}", headers=worker_headers)
    assert reread.json()["can_edit"] is True


async def test_worker_cannot_approve_return_or_list_submissions(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker_headers, _manager_headers = await _setup_worker_with_hours(
        client, make_user, make_project, auth_headers
    )
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)

    approve = await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/approve",
        headers=worker_headers,
        params={"user_id": worker_id},
    )
    ret = await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/return",
        headers=worker_headers,
        params={"user_id": worker_id},
        json={"comment": "..."},
    )
    submissions = await client.get("/api/v1/timesheets/submissions", headers=worker_headers)

    assert approve.status_code == 403
    assert ret.status_code == 403
    assert submissions.status_code == 403


async def test_admin_only_cannot_approve_or_view_others_week(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker_headers, _manager_headers = await _setup_worker_with_hours(
        client, make_user, make_project, auth_headers
    )
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)
    admin_headers = auth_headers(await make_user(roles=ADMIN_ONLY))

    view = await client.get(
        f"/api/v1/timesheets/weeks/{A_MONDAY}",
        headers=admin_headers,
        params={"user_id": worker_id},
    )
    approve = await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/approve",
        headers=admin_headers,
        params={"user_id": worker_id},
    )

    assert view.status_code == 403
    assert approve.status_code == 403


async def test_submissions_list_includes_a_submitted_week(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker_headers, manager_headers = await _setup_worker_with_hours(
        client, make_user, make_project, auth_headers
    )
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)

    submissions = await client.get("/api/v1/timesheets/submissions", headers=manager_headers)

    assert submissions.status_code == 200
    matching = next(s for s in submissions.json() if s["user"]["id"] == worker_id)
    assert matching["week_start"] == A_MONDAY
    assert matching["status"] == "submitted"
    assert matching["total_hours"] == "8.00"


async def test_submissions_scope_mine_excludes_other_managers_projects(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    other_manager = await make_user(roles=MANAGER)
    manager = await make_user(roles=MANAGER)
    manager_headers = auth_headers(manager)
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project(manager_id=other_manager.id)
    await _add_member(client, manager_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, manager_headers, str(project.id))
    await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "8.00"}]},
    )
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)

    mine = await client.get(
        "/api/v1/timesheets/submissions", headers=manager_headers, params={"scope": "mine"}
    )
    everyone = await client.get(
        "/api/v1/timesheets/submissions", headers=manager_headers, params={"scope": "all"}
    )

    assert mine.status_code == 200
    assert mine.json() == []
    assert everyone.status_code == 200
    assert any(s["user"]["id"] == str(worker.id) for s in everyone.json())


# --- Team overview ---


async def test_team_overview_defaults_to_the_managers_own_projects(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    manager = await make_user(roles=MANAGER)
    manager_headers = auth_headers(manager)
    other_manager = await make_user(roles=MANAGER)
    mine = await make_project(manager_id=manager.id, name="Mine")
    await make_project(manager_id=other_manager.id, name="Theirs")

    response = await client.get("/api/v1/timesheets/team/2026/9", headers=manager_headers)

    assert response.status_code == 200
    body = response.json()
    project_ids = {p["project"]["id"] for p in body["projects"]}
    assert project_ids == {str(mine.id)}
    assert "counts" in body and "weeks" in body


async def test_team_overview_scope_all_is_available_to_any_manager(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    manager = await make_user(roles=MANAGER)
    admin = await make_user(roles=ADMIN)
    await make_project(manager_id=manager.id)

    as_manager = await client.get(
        "/api/v1/timesheets/team/2026/9",
        headers=auth_headers(manager),
        params={"scope": "all"},
    )
    as_admin = await client.get(
        "/api/v1/timesheets/team/2026/9", headers=auth_headers(admin), params={"scope": "all"}
    )

    assert as_manager.status_code == 200
    assert as_admin.status_code == 200


async def test_team_overview_requires_manager_access(
    client: AsyncClient, make_user: UserFactory, auth_headers: AuthHeaders
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    response = await client.get("/api/v1/timesheets/team/2026/9", headers=auth_headers(worker))
    assert response.status_code == 403


# --- Billing periods ---


async def test_send_project_month_to_billing_and_reopen(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin = await make_user(roles=ADMIN)
    admin_headers = auth_headers(admin)
    manager = await make_user(roles=MANAGER)
    manager_headers = auth_headers(manager)
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project(manager_id=manager.id)
    await _add_member(client, manager_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, manager_headers, str(project.id))
    await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "8.00"}]},
    )
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/approve",
        headers=manager_headers,
        params={"user_id": worker_id},
    )

    sent = await client.post(
        "/api/v1/timesheets/billing-periods",
        headers=manager_headers,
        json={"project_id": str(project.id), "year": 2026, "month": 9},
    )
    assert sent.status_code == 201
    assert sent.json()["status"] == "sent"

    already_sent = await client.post(
        "/api/v1/timesheets/billing-periods",
        headers=manager_headers,
        json={"project_id": str(project.id), "year": 2026, "month": 9},
    )
    assert already_sent.status_code == 409

    forbidden_reopen = await client.request(
        "DELETE",
        f"/api/v1/timesheets/billing-periods/{project.id}/2026-09-01",
        headers=manager_headers,
    )
    assert forbidden_reopen.status_code == 403

    reopened = await client.request(
        "DELETE",
        f"/api/v1/timesheets/billing-periods/{project.id}/2026-09-01",
        headers=admin_headers,
    )
    assert reopened.status_code == 204


async def test_send_project_month_to_billing_not_ready(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    manager = await make_user(roles=MANAGER)
    project = await make_project(manager_id=manager.id)

    response = await client.post(
        "/api/v1/timesheets/billing-periods",
        headers=auth_headers(manager),
        json={"project_id": str(project.id), "year": 2026, "month": 9},
    )

    assert response.status_code == 409


async def test_send_project_month_to_billing_by_a_different_manager_is_allowed(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    manager = await make_user(roles=MANAGER)
    manager_headers = auth_headers(manager)
    other_manager = await make_user(roles=MANAGER)
    other_manager_headers = auth_headers(other_manager)
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project(manager_id=manager.id)
    await _add_member(client, manager_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, manager_headers, str(project.id))
    await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "8.00"}]},
    )
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/approve",
        headers=other_manager_headers,
        params={"user_id": worker_id},
    )

    response = await client.post(
        "/api/v1/timesheets/billing-periods",
        headers=other_manager_headers,
        json={"project_id": str(project.id), "year": 2026, "month": 9},
    )

    assert response.status_code == 201


async def test_reopen_unknown_billing_period_returns_404(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin = await make_user(roles=ADMIN)
    project = await make_project()

    response = await client.request(
        "DELETE",
        f"/api/v1/timesheets/billing-periods/{project.id}/2026-09-01",
        headers=auth_headers(admin),
    )

    assert response.status_code == 404


async def test_billing_periods_require_manager_access(
    client: AsyncClient, make_user: UserFactory, make_project: ProjectFactory
) -> None:
    project = await make_project()
    response = await client.post(
        "/api/v1/timesheets/billing-periods",
        json={"project_id": str(project.id), "year": 2026, "month": 9},
    )
    assert response.status_code == 401


async def test_anonymous_cannot_list_billing_periods(client: AsyncClient) -> None:
    response = await client.get("/api/v1/timesheets/billing-periods")
    assert response.status_code == 401


@pytest.mark.parametrize("roles", [MANAGER, EMPLOYEE])
async def test_non_admin_cannot_list_billing_periods(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    roles: frozenset[UserRole],
) -> None:
    headers = auth_headers(await make_user(roles=roles))
    response = await client.get("/api/v1/timesheets/billing-periods", headers=headers)
    assert response.status_code == 403


async def test_admin_can_list_and_filter_billing_periods(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin = await make_user(roles=ADMIN)
    admin_headers = auth_headers(admin)
    manager = await make_user(roles=MANAGER)
    manager_headers = auth_headers(manager)
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project(manager_id=manager.id)
    await _add_member(client, manager_headers, str(project.id), str(worker.id))
    item_id = await _normal_hours_item_id(client, manager_headers, str(project.id))
    await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "8.00"}]},
    )
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/approve",
        headers=manager_headers,
        params={"user_id": worker_id},
    )
    await client.post(
        "/api/v1/timesheets/billing-periods",
        headers=manager_headers,
        json={"project_id": str(project.id), "year": 2026, "month": 9},
    )

    response = await client.get(
        "/api/v1/timesheets/billing-periods",
        headers=admin_headers,
        params={"project_id": str(project.id), "limit": 10, "offset": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 0
    item = body["items"][0]
    assert item["project_id"] == str(project.id)
    assert item["period_start"] == "2026-09-01"
    assert item["sent_by_id"] == str(manager.id)
    assert item["sent_by_name"] == manager.name


async def test_export_billing_period_csv_requires_admin(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    project = await make_project()

    anonymous = await client.get(
        f"/api/v1/timesheets/billing-periods/{project.id}/2026-09-01/export.csv"
    )
    assert anonymous.status_code == 401

    manager_headers = auth_headers(await make_user(roles=MANAGER))
    forbidden = await client.get(
        f"/api/v1/timesheets/billing-periods/{project.id}/2026-09-01/export.csv",
        headers=manager_headers,
    )
    assert forbidden.status_code == 403


async def test_export_billing_period_csv_unknown_period_returns_404(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()

    response = await client.get(
        f"/api/v1/timesheets/billing-periods/{project.id}/2026-09-01/export.csv",
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_export_billing_period_csv_contains_both_sources(
    client: AsyncClient,
    bus: Bus,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    admin = await make_user(roles=ADMIN)
    admin_headers = auth_headers(admin)
    manager = await make_user(roles=MANAGER)
    manager_headers = auth_headers(manager)
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    project = await make_project(manager_id=manager.id)
    await _add_member(client, manager_headers, str(project.id), str(worker.id))

    item_id = await _normal_hours_item_id(client, manager_headers, str(project.id))
    await client.put(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/entries",
        headers=worker_headers,
        json={"changes": [{"billing_item_id": item_id, "date": A_MONDAY, "quantity": "8.00"}]},
    )
    await client.post(f"/api/v1/timesheets/weeks/{A_MONDAY}/submit", headers=worker_headers)
    worker_id = (await client.get("/api/v1/users/me", headers=worker_headers)).json()["id"]
    await client.post(
        f"/api/v1/timesheets/weeks/{A_MONDAY}/approve",
        headers=manager_headers,
        params={"user_id": worker_id},
    )

    billing_items = await bus.query(ListProjectBillingItems(project_id=project.id))
    purchasing_id = next(
        item.id for item in billing_items if item.preset == BillingItemPreset.PURCHASING_EXPENSES
    )
    report = await bus.execute(
        CreateExpenseReport(user_id=worker.id, project_id=project.id, year=2026, month=9)
    )
    await bus.execute(
        SaveExpenseReportLines(
            report_id=report.id,
            actor_id=worker.id,
            lines=(
                ExpenseLineChange(
                    line_id=None,
                    billing_item_id=purchasing_id,
                    expense_date=date(2026, 9, 5),
                    amount=Decimal("42.50"),
                    description="Taxi",
                    vendor="City Cabs",
                    document_no="INV-1",
                ),
            ),
        )
    )
    await bus.execute(SubmitExpenseReport(report_id=report.id, actor_id=worker.id))
    await bus.execute(ApproveExpenseReport(report_id=report.id, reviewer_id=manager.id))

    await client.post(
        "/api/v1/timesheets/billing-periods",
        headers=manager_headers,
        json={"project_id": str(project.id), "year": 2026, "month": 9},
    )

    response = await client.get(
        f"/api/v1/timesheets/billing-periods/{project.id}/2026-09-01/export.csv",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="billing-{project.id}-2026-09-01.csv"'
    )
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "Date",
        "User",
        "Email",
        "Billing item",
        "Unit",
        "Quantity",
        "Currency",
        "Description",
        "Vendor",
        "Document no.",
    ]
    data_rows = rows[1:]
    assert len(data_rows) == 2
    hours_row = next(row for row in data_rows if row[4] == "hour")
    assert hours_row[1] == worker.name
    assert hours_row[5] == "8.00"
    expense_row = next(row for row in data_rows if row[4] == "amount")
    assert expense_row[1] == worker.name
    assert expense_row[5] == "42.50"
    assert expense_row[6] == project.customer.currency
    assert expense_row[7] == "Taxi"
    assert expense_row[8] == "City Cabs"
    assert expense_row[9] == "INV-1"
