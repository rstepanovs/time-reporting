"""Tests for the demo data seed and the ``time-reporting seed-demo`` command."""

import io
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from support import UserFactory
from time_reporting.cli import main
from time_reporting.core.cqrs import Bus
from time_reporting.core.passwords import verify_password
from time_reporting.modules.customers.contracts import ListCustomers
from time_reporting.modules.projects.contracts import (
    BillingItemPreset,
    ListProjectBillingItems,
    ListProjectMembers,
    ListProjects,
)
from time_reporting.modules.timesheets.contracts import CountTimeEntries, GetTimesheetWeek
from time_reporting.modules.users.contracts import GetUserById, GetUserCredentialsByEmail, UserRole
from time_reporting.modules.work_calendar.contracts import ListNonWorkingDays, NonWorkingDayKind
from time_reporting.seed import (
    DEFAULT_DEMO_PASSWORD,
    DEMO_BILLING_RATES,
    DEMO_CUSTOMERS,
    DEMO_PROJECTS,
    DEMO_PURCHASING_MARKUP,
    DEMO_TIME_ENTRY_ROLES,
    DEMO_USERS,
    DemoCustomer,
    DemoProject,
    DemoUser,
    SeedReport,
    seed_demo_data,
)

# Seeding uses this as "today" so holiday counts and week boundaries are deterministic; it is
# itself a Monday.
SEED_TODAY = date(2026, 9, 14)

# The test database may already hold the real demo records (it doubles as the dev database), so
# the seed runs against uniquely renamed copies of them.


def _unique_users(suffix: str) -> tuple[DemoUser, ...]:
    return tuple(replace(user, email=f"{suffix}.{user.email}") for user in DEMO_USERS)


def _unique_customers(suffix: str) -> tuple[DemoCustomer, ...]:
    return tuple(
        replace(customer, create=replace(customer.create, name=f"{customer.create.name} {suffix}"))
        for customer in DEMO_CUSTOMERS
    )


def _unique_projects(suffix: str) -> tuple[DemoProject, ...]:
    return tuple(
        replace(
            project,
            customer_name=f"{project.customer_name} {suffix}",
            name=f"{project.name} {suffix}",
            member_emails=tuple(f"{suffix}.{email}" for email in project.member_emails),
            manager_email=(f"{suffix}.{project.manager_email}" if project.manager_email else None),
        )
        for project in DEMO_PROJECTS
    )


def test_demo_data_covers_every_role_and_an_archived_customer() -> None:
    assert {user.role for user in DEMO_USERS} == set(UserRole)
    assert {customer.archived for customer in DEMO_CUSTOMERS} == {True, False}
    assert {project.archived for project in DEMO_PROJECTS} == {True, False}

    customer_names = {customer.create.name for customer in DEMO_CUSTOMERS}
    assert {project.customer_name for project in DEMO_PROJECTS} <= customer_names
    user_emails = {user.email for user in DEMO_USERS}
    assert all(email in user_emails for project in DEMO_PROJECTS for email in project.member_emails)


async def test_seed_creates_users_customers_and_projects(bus: Bus) -> None:
    suffix = uuid4().hex[:8]
    users, customers, projects = (
        _unique_users(suffix),
        _unique_customers(suffix),
        _unique_projects(suffix),
    )

    report = await seed_demo_data(
        bus, users=users, customers=customers, projects=projects, today=SEED_TODAY
    )

    assert report.created_users == [user.email for user in users]
    assert report.created_customers == [customer.create.name for customer in customers]
    assert report.created_projects == [project.name for project in projects]
    assert (report.existing_users, report.existing_customers, report.existing_projects) == (
        [],
        [],
        [],
    )
    for user in users:
        credentials = await bus.query(GetUserCredentialsByEmail(email=user.email))
        assert credentials is not None
        assert (await verify_password(DEFAULT_DEMO_PASSWORD, credentials.password_hash))[0]
        stored = await bus.query(GetUserById(user_id=credentials.id))
        assert stored is not None
        assert stored.role is user.role

    customer_page = await bus.query(ListCustomers(limit=1000, offset=0, include_inactive=True))
    active_by_name = {customer.name: customer.is_active for customer in customer_page.items}
    for customer in customers:
        assert active_by_name[customer.create.name] is not customer.archived

    project_page = await bus.query(ListProjects(limit=1000, offset=0, include_inactive=True))
    projects_by_name = {project.name: project for project in project_page.items}
    for project in projects:
        stored_project = projects_by_name[project.name]
        assert stored_project.is_active is not project.archived
        assert stored_project.customer.name == project.customer_name
        if project.manager_email:
            assert stored_project.manager is not None
            assert stored_project.manager.email == project.manager_email
        else:
            assert stored_project.manager is None

        members = await bus.query(ListProjectMembers(project_id=stored_project.id))
        assert {member.email for member in members} == set(project.member_emails)

        billing_items = await bus.query(
            ListProjectBillingItems(project_id=stored_project.id, include_inactive=True)
        )
        rates_by_preset = {item.preset: item.unit_rate for item in billing_items}
        markups_by_preset = {item.preset: item.markup_percent for item in billing_items}
        if project.billing_rates:
            for preset, rate in DEMO_BILLING_RATES.items():
                assert rates_by_preset[preset] == rate
            assert (
                markups_by_preset[BillingItemPreset.PURCHASING_EXPENSES] == DEMO_PURCHASING_MARKUP
            )
            assert rates_by_preset[BillingItemPreset.OTHER_EXPENSES] is None
        else:
            assert all(rate is None for rate in rates_by_preset.values())

        custom_names = {item.name for item in billing_items if item.preset is None}
        assert custom_names == {item.name for item in project.custom_billing_items}
        for demo_item in project.custom_billing_items:
            stored_item = next(item for item in billing_items if item.name == demo_item.name)
            assert stored_item.unit == demo_item.unit
            assert stored_item.unit_rate == demo_item.unit_rate

    # Calendar: this and next year's public holidays plus one bridge day (the calendar is shared,
    # not namespaced by suffix, but the test transaction rolls back so it starts out empty).
    assert report.imported_holidays > 0
    assert report.created_bridge_day is True
    non_working_days = await bus.query(ListNonWorkingDays(year=SEED_TODAY.year))
    assert any(day.kind is NonWorkingDayKind.BRIDGE_DAY for day in non_working_days)

    # Time entries: only workers/PMs get demo hours booked, not admins. Normal hours are booked on
    # every working day from Jul 1 through SEED_TODAY (2026-09-14) — 54 working days, no DE public
    # holidays fall in that window — plus one overtime and one travel entry per month (the first
    # and last working day booked that month); SEED_TODAY is itself the last working day booked
    # for September, so this week also carries a travel entry alongside the normal hours.
    time_entry_users = {user for user in users if user.role in DEMO_TIME_ENTRY_ROLES}
    assert set(report.seeded_time_entries_for) == {user.email for user in time_entry_users}
    for user in time_entry_users:
        credentials = await bus.query(GetUserCredentialsByEmail(email=user.email))
        assert credentials is not None
        assert await bus.query(CountTimeEntries(user_id=credentials.id)) == 60
        this_week = await bus.query(
            GetTimesheetWeek(
                user_id=credentials.id, week_start=SEED_TODAY, viewer_id=credentials.id
            )
        )
        booked_dates = {entry.date for row in this_week.rows for entry in row.entries}
        assert booked_dates == {SEED_TODAY}
        entries_by_preset = {
            row.billing_item.preset: entry for row in this_week.rows for entry in row.entries
        }
        assert entries_by_preset[BillingItemPreset.NORMAL_HOURS].quantity == Decimal("8.00")
        assert entries_by_preset[BillingItemPreset.TRAVEL_TIME].quantity == Decimal("3.00")
    for user in users:
        if user.role not in DEMO_TIME_ENTRY_ROLES:
            credentials = await bus.query(GetUserCredentialsByEmail(email=user.email))
            assert credentials is not None
            assert await bus.query(CountTimeEntries(user_id=credentials.id)) == 0


async def test_seed_is_idempotent(bus: Bus) -> None:
    suffix = uuid4().hex[:8]
    users, customers, projects = (
        _unique_users(suffix),
        _unique_customers(suffix),
        _unique_projects(suffix),
    )
    await seed_demo_data(bus, users=users, customers=customers, projects=projects, today=SEED_TODAY)

    report = await seed_demo_data(
        bus, users=users, customers=customers, projects=projects, today=SEED_TODAY
    )

    assert report == SeedReport(
        existing_users=[user.email for user in users],
        existing_customers=[customer.create.name for customer in customers],
        existing_projects=[project.name for project in projects],
    )


async def test_seed_leaves_an_existing_user_untouched(bus: Bus, make_user: UserFactory) -> None:
    users = _unique_users(uuid4().hex[:8])
    admin_seat = next(user for user in users if user.role is UserRole.ADMIN)
    existing = await make_user(email=admin_seat.email, role=UserRole.WORKER, name="Someone Else")

    report = await seed_demo_data(bus, users=users, customers=(), projects=())

    assert report.existing_users == [admin_seat.email]
    stored = await bus.query(GetUserById(user_id=existing.id))
    assert stored is not None
    assert (stored.role, stored.name) == (UserRole.WORKER, "Someone Else")


# --- main(): output and input validation, without touching the database ---


def _stub_seed(monkeypatch: pytest.MonkeyPatch, report: SeedReport) -> list[str]:
    passwords: list[str] = []

    async def fake_seed_demo_in_database(*, password: str) -> SeedReport:
        passwords.append(password)
        return report

    monkeypatch.setattr("time_reporting.cli._seed_demo_in_database", fake_seed_demo_in_database)
    return passwords


def test_seed_demo_command_reports_records_and_default_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    passwords = _stub_seed(
        monkeypatch,
        SeedReport(
            created_users=["admin@example.com"],
            existing_users=["worker@example.com"],
            existing_customers=["Acme Corporation"],
            existing_projects=["Website Revamp"],
        ),
    )

    exit_code = main(["seed-demo"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert passwords == [DEFAULT_DEMO_PASSWORD]
    assert "Created user admin@example.com" in out
    assert "Skipped user worker@example.com (already exists)" in out
    assert "Skipped customer Acme Corporation (already exists)" in out
    assert "Skipped project Website Revamp (already exists)" in out
    assert f"password: {DEFAULT_DEMO_PASSWORD}" in out


def test_seed_demo_command_does_not_echo_a_password_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("my-own-demo-password\n"))
    passwords = _stub_seed(monkeypatch, SeedReport(created_users=["admin@example.com"]))

    exit_code = main(["seed-demo", "--password-stdin"])

    assert exit_code == 0
    assert passwords == ["my-own-demo-password"]
    assert "my-own-demo-password" not in capsys.readouterr().out


def test_seed_demo_command_rejects_a_short_password_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    passwords = _stub_seed(monkeypatch, SeedReport())

    exit_code = main(["seed-demo", "--password-stdin"])

    assert exit_code == 1
    assert passwords == []
    assert "password must be" in capsys.readouterr().err
