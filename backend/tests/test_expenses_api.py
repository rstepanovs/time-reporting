from pathlib import Path
from typing import Any, cast

import pytest
from httpx import AsyncClient

from support import ADMIN, EMPLOYEE, MANAGER, AuthHeaders, ProjectFactory, UserFactory
from time_reporting.core.config import get_settings
from time_reporting.modules.projects.contracts import BillingItemPreset

YEAR = 2026
MONTH = 9

_PDF_BYTES = b"%PDF-1.4 not a real pdf"


@pytest.fixture(autouse=True)
def _isolated_attachments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every test in this file goes through the real HTTP router, which builds
    ``ExpenseAttachmentStorage`` from the process-wide ``get_settings()`` — without this, an
    upload test would write real files under the repo's working directory."""
    patched = get_settings().model_copy(update={"attachment_dir": str(tmp_path)})
    monkeypatch.setattr("time_reporting.modules.expenses.service.get_settings", lambda: patched)


async def _add_member(
    client: AsyncClient, headers: dict[str, str], project_id: str, user_id: str
) -> None:
    response = await client.post(
        f"/api/v1/projects/{project_id}/members", headers=headers, json={"user_id": user_id}
    )
    assert response.status_code == 201


async def _purchasing_item_id(client: AsyncClient, headers: dict[str, str], project_id: str) -> str:
    response = await client.get(f"/api/v1/projects/{project_id}/billing-items", headers=headers)
    item = next(
        i for i in response.json() if i["preset"] == BillingItemPreset.PURCHASING_EXPENSES.value
    )
    return str(item["id"])


async def _create_report(
    client: AsyncClient, headers: dict[str, str], project_id: str
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/expenses/reports",
        headers=headers,
        json={"project_id": project_id, "year": YEAR, "month": MONTH},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


async def test_worker_can_create_and_manage_their_own_report(
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
    item_id = await _purchasing_item_id(client, admin_headers, str(project.id))

    report = await _create_report(client, worker_headers, str(project.id))
    assert report["status"] == "draft"
    assert report["can_edit"] is True

    saved = await client.put(
        f"/api/v1/expenses/reports/{report['id']}/lines",
        headers=worker_headers,
        json={
            "lines": [
                {
                    "billing_item_id": item_id,
                    "expense_date": f"{YEAR}-{MONTH:02d}-05",
                    "amount": "42.50",
                    "description": "Taxi",
                    "vendor": "City Cabs",
                }
            ]
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["total"] == "42.50"
    assert body["lines"][0]["amount"] == "42.50"
    assert body["lines"][0]["vendor"] == "City Cabs"

    fetched = await client.get(f"/api/v1/expenses/reports/{report['id']}", headers=worker_headers)
    assert fetched.status_code == 200
    assert fetched.json()["total"] == "42.50"

    submitted = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/submit", headers=worker_headers
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"


async def test_creating_a_duplicate_report_conflicts(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    worker_headers = auth_headers(worker)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    await _create_report(client, worker_headers, str(project.id))

    duplicate = await client.post(
        "/api/v1/expenses/reports",
        headers=worker_headers,
        json={"project_id": str(project.id), "year": YEAR, "month": MONTH},
    )

    assert duplicate.status_code == 409


async def test_creating_a_report_for_a_project_you_dont_belong_to_is_rejected(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    project = await make_project()

    response = await client.post(
        "/api/v1/expenses/reports",
        headers=auth_headers(worker),
        json={"project_id": str(project.id), "year": YEAR, "month": MONTH},
    )

    assert response.status_code == 400


async def test_a_stranger_cannot_read_another_users_report(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    stranger = await make_user(roles=EMPLOYEE)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    report = await _create_report(client, auth_headers(worker), str(project.id))

    response = await client.get(
        f"/api/v1/expenses/reports/{report['id']}", headers=auth_headers(stranger)
    )

    assert response.status_code == 404


async def test_a_manager_can_read_but_not_edit_another_users_report(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    manager = await make_user(roles=MANAGER)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    report = await _create_report(client, auth_headers(worker), str(project.id))

    read = await client.get(
        f"/api/v1/expenses/reports/{report['id']}", headers=auth_headers(manager)
    )
    assert read.status_code == 200
    assert read.json()["can_edit"] is False

    # A manager isn't the owner; a write attempt on someone else's report is treated the same
    # as an unknown report_id (404), not a distinct 403 — see `ExpenseService._get_own_report`.
    write = await client.put(
        f"/api/v1/expenses/reports/{report['id']}/lines",
        headers=auth_headers(manager),
        json={"lines": []},
    )
    assert write.status_code == 404


async def test_submit_approve_and_return_flow(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    manager = await make_user(roles=MANAGER)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    report = await _create_report(client, auth_headers(worker), str(project.id))
    await client.post(
        f"/api/v1/expenses/reports/{report['id']}/submit", headers=auth_headers(worker)
    )

    self_approve = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/approve", headers=auth_headers(worker)
    )
    assert self_approve.status_code == 403

    # An empty comment is rejected at the HTTP boundary (422) before ever reaching the
    # domain-level ``ExpenseReturnCommentRequiredError`` check.
    missing_comment = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/return",
        headers=auth_headers(manager),
        json={"comment": ""},
    )
    assert missing_comment.status_code == 422

    returned = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/return",
        headers=auth_headers(manager),
        json={"comment": "Missing receipt"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"

    await client.post(
        f"/api/v1/expenses/reports/{report['id']}/submit", headers=auth_headers(worker)
    )
    approved = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/approve", headers=auth_headers(manager)
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


async def test_submissions_lists_and_filters_by_scope(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    manager = await make_user(roles=MANAGER)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    report = await _create_report(client, auth_headers(worker), str(project.id))
    await client.post(
        f"/api/v1/expenses/reports/{report['id']}/submit", headers=auth_headers(worker)
    )

    forbidden = await client.get("/api/v1/expenses/submissions", headers=auth_headers(worker))
    assert forbidden.status_code == 403

    submissions = await client.get("/api/v1/expenses/submissions", headers=auth_headers(manager))
    assert submissions.status_code == 200
    assert any(item["id"] == report["id"] for item in submissions.json())


async def test_upload_and_download_attachment_round_trip(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    report = await _create_report(client, auth_headers(worker), str(project.id))

    upload = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/attachments",
        headers=auth_headers(worker),
        files={"file": ("receipt.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert upload.status_code == 201
    attachment = upload.json()
    assert attachment["file_name"] == "receipt.pdf"

    download = await client.get(
        f"/api/v1/expenses/attachments/{attachment['id']}", headers=auth_headers(worker)
    )
    assert download.status_code == 200
    assert download.content == _PDF_BYTES
    assert download.headers["content-type"] == "application/pdf"

    deleted = await client.delete(
        f"/api/v1/expenses/attachments/{attachment['id']}", headers=auth_headers(worker)
    )
    assert deleted.status_code == 204

    gone = await client.get(
        f"/api/v1/expenses/attachments/{attachment['id']}", headers=auth_headers(worker)
    )
    assert gone.status_code == 404


async def test_upload_rejects_disallowed_content_type(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    report = await _create_report(client, auth_headers(worker), str(project.id))

    upload = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/attachments",
        headers=auth_headers(worker),
        files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
    )

    assert upload.status_code == 415


async def test_a_stranger_cannot_download_another_users_attachment(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    stranger = await make_user(roles=EMPLOYEE)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))
    report = await _create_report(client, auth_headers(worker), str(project.id))
    upload = await client.post(
        f"/api/v1/expenses/reports/{report['id']}/attachments",
        headers=auth_headers(worker),
        files={"file": ("receipt.pdf", _PDF_BYTES, "application/pdf")},
    )
    attachment_id = upload.json()["id"]

    response = await client.get(
        f"/api/v1/expenses/attachments/{attachment_id}", headers=auth_headers(stranger)
    )

    assert response.status_code == 404


async def test_options_lists_the_workers_amount_billing_items(
    client: AsyncClient,
    make_user: UserFactory,
    make_project: ProjectFactory,
    auth_headers: AuthHeaders,
) -> None:
    worker = await make_user(roles=EMPLOYEE)
    admin_headers = auth_headers(await make_user(roles=ADMIN))
    project = await make_project()
    await _add_member(client, admin_headers, str(project.id), str(worker.id))

    response = await client.get("/api/v1/expenses/options", headers=auth_headers(worker))

    assert response.status_code == 200
    options = response.json()
    assert len(options) == 1
    units = {item["unit"] for item in options[0]["billing_items"]}
    assert units == {"amount"}
