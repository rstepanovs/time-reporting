"""Tests for the demo data seed and the ``time-reporting seed-demo`` command."""

import io
from dataclasses import replace
from uuid import uuid4

import pytest

from support import UserFactory
from time_reporting.cli import main
from time_reporting.core.cqrs import Bus
from time_reporting.core.passwords import verify_password
from time_reporting.modules.customers.contracts import ListCustomers
from time_reporting.modules.users.contracts import GetUserById, GetUserCredentialsByEmail, UserRole
from time_reporting.seed import (
    DEFAULT_DEMO_PASSWORD,
    DEMO_CUSTOMERS,
    DEMO_USERS,
    DemoCustomer,
    DemoUser,
    SeedReport,
    seed_demo_data,
)

# The test database may already hold the real demo records (it doubles as the dev database), so
# the seed runs against uniquely renamed copies of them.


def _unique_users() -> tuple[DemoUser, ...]:
    suffix = uuid4().hex[:8]
    return tuple(replace(user, email=f"{suffix}.{user.email}") for user in DEMO_USERS)


def _unique_customers() -> tuple[DemoCustomer, ...]:
    suffix = uuid4().hex[:8]
    return tuple(
        replace(customer, create=replace(customer.create, name=f"{customer.create.name} {suffix}"))
        for customer in DEMO_CUSTOMERS
    )


def test_demo_data_covers_every_role_and_an_archived_customer() -> None:
    assert {user.role for user in DEMO_USERS} == set(UserRole)
    assert {customer.archived for customer in DEMO_CUSTOMERS} == {True, False}


async def test_seed_creates_users_and_customers(bus: Bus) -> None:
    users, customers = _unique_users(), _unique_customers()

    report = await seed_demo_data(bus, users=users, customers=customers)

    assert report == SeedReport(
        created_users=[user.email for user in users],
        created_customers=[customer.create.name for customer in customers],
    )
    for user in users:
        credentials = await bus.query(GetUserCredentialsByEmail(email=user.email))
        assert credentials is not None
        assert (await verify_password(DEFAULT_DEMO_PASSWORD, credentials.password_hash))[0]
        stored = await bus.query(GetUserById(user_id=credentials.id))
        assert stored is not None
        assert stored.role is user.role

    page = await bus.query(ListCustomers(limit=1000, offset=0, include_inactive=True))
    active_by_name = {customer.name: customer.is_active for customer in page.items}
    for customer in customers:
        assert active_by_name[customer.create.name] is not customer.archived


async def test_seed_is_idempotent(bus: Bus) -> None:
    users, customers = _unique_users(), _unique_customers()
    await seed_demo_data(bus, users=users, customers=customers)

    report = await seed_demo_data(bus, users=users, customers=customers)

    assert report == SeedReport(
        existing_users=[user.email for user in users],
        existing_customers=[customer.create.name for customer in customers],
    )


async def test_seed_leaves_an_existing_user_untouched(bus: Bus, make_user: UserFactory) -> None:
    users = _unique_users()
    admin_seat = next(user for user in users if user.role is UserRole.ADMIN)
    existing = await make_user(email=admin_seat.email, role=UserRole.WORKER, name="Someone Else")

    report = await seed_demo_data(bus, users=users, customers=())

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
        ),
    )

    exit_code = main(["seed-demo"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert passwords == [DEFAULT_DEMO_PASSWORD]
    assert "Created user admin@example.com" in out
    assert "Skipped user worker@example.com (already exists)" in out
    assert "Skipped customer Acme Corporation (already exists)" in out
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
