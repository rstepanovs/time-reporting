"""Tests for the ``time-reporting`` CLI: creating the first administrator."""

import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from support import DEFAULT_PASSWORD, UserFactory
from time_reporting.cli import create_admin, main
from time_reporting.core.cqrs import Bus
from time_reporting.modules.users.contracts import EmailAlreadyExistsError, UserDTO, UserRole
from time_reporting.modules.work_calendar.contracts import HolidayCountryNotSupportedError

# --- create_admin(): the create-admin path through the bus, against a real (rolled-back) DB ---


async def test_create_admin_creates_an_active_admin(bus: Bus) -> None:
    admin = await create_admin(
        bus, name="Root", email="root@example.com", password=DEFAULT_PASSWORD
    )

    assert admin.role is UserRole.ADMIN
    assert admin.email == "root@example.com"
    assert admin.is_active
    assert admin.token_version == 0


async def test_create_admin_rejects_duplicate_email(bus: Bus, make_user: UserFactory) -> None:
    await make_user(email="taken@example.com")

    with pytest.raises(EmailAlreadyExistsError):
        await create_admin(
            bus, name="Someone", email="taken@example.com", password=DEFAULT_PASSWORD
        )


# --- main(): argument parsing and input validation, without touching the database ---


def _fake_admin(*, email: str) -> UserDTO:
    now = datetime.now(UTC)
    return UserDTO(
        id=uuid4(),
        name="Root",
        email=email,
        role=UserRole.ADMIN,
        is_active=True,
        token_version=0,
        last_login_at=None,
        created_at=now,
        updated_at=now,
    )


def _stub_database(monkeypatch: pytest.MonkeyPatch, outcome: UserDTO | Exception) -> None:
    """Replace the DB-touching half of create-admin, so validation tests stay database-free."""

    async def fake_create_admin_in_database(*, name: str, email: str, password: str) -> UserDTO:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(
        "time_reporting.cli._create_admin_in_database", fake_create_admin_in_database
    )


def test_missing_required_arguments_exit_nonzero() -> None:
    with pytest.raises(SystemExit):
        main(["create-admin", "--email", "root@example.com"])


def test_unknown_command_exits_nonzero() -> None:
    with pytest.raises(SystemExit):
        main(["not-a-command"])


def test_rejects_invalid_email(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["create-admin", "--email", "not-an-email", "--name", "Root"])

    assert exit_code == 1
    assert "invalid email" in capsys.readouterr().err


def test_rejects_blank_name(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["create-admin", "--email", "root@example.com", "--name", "   "])

    assert exit_code == 1
    assert "name must be" in capsys.readouterr().err


def test_rejects_password_from_stdin_that_is_too_short(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))

    exit_code = main(
        ["create-admin", "--email", "root@example.com", "--name", "Root", "--password-stdin"]
    )

    assert exit_code == 1
    assert "password must be" in capsys.readouterr().err


def test_mismatched_interactive_passwords_are_rejected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = iter([DEFAULT_PASSWORD, "a-different-password"])
    monkeypatch.setattr("getpass.getpass", lambda *_args, **_kwargs: next(responses))

    exit_code = main(["create-admin", "--email", "root@example.com", "--name", "Root"])

    assert exit_code == 1
    assert "do not match" in capsys.readouterr().err


def test_successful_creation_prints_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{DEFAULT_PASSWORD}\n"))
    _stub_database(monkeypatch, _fake_admin(email="root@example.com"))

    exit_code = main(
        ["create-admin", "--email", "root@example.com", "--name", "Root", "--password-stdin"]
    )

    assert exit_code == 0
    assert "Created administrator root@example.com" in capsys.readouterr().out


def test_duplicate_email_from_the_database_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{DEFAULT_PASSWORD}\n"))
    _stub_database(monkeypatch, EmailAlreadyExistsError("root@example.com"))

    exit_code = main(
        ["create-admin", "--email", "root@example.com", "--name", "Root", "--password-stdin"]
    )

    assert exit_code == 1
    assert "already exists" in capsys.readouterr().err


# --- import-holidays ---


def _stub_holiday_import(monkeypatch: pytest.MonkeyPatch, outcome: int | Exception) -> None:
    async def fake_import_holidays_in_database(*, year: int) -> int:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(
        "time_reporting.cli._import_holidays_in_database", fake_import_holidays_in_database
    )


def test_import_holidays_prints_the_added_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_holiday_import(monkeypatch, 9)

    exit_code = main(["import-holidays", "--year", "2026"])

    assert exit_code == 0
    assert "Added 9 public holiday(s) for 2026" in capsys.readouterr().out


def test_import_holidays_reports_unsupported_country(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_holiday_import(monkeypatch, HolidayCountryNotSupportedError("ZZ", None))

    exit_code = main(["import-holidays", "--year", "2026"])

    assert exit_code == 1
    assert "not supported" in capsys.readouterr().err
