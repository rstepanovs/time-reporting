"""Administrative command-line interface, installed as ``time-reporting``."""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from pydantic import EmailStr, TypeAdapter, ValidationError

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.core.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from time_reporting.db.session import SessionFactory, engine
from time_reporting.modules.expenses.contracts import ListAttachmentStorageKeys
from time_reporting.modules.expenses.storage import ExpenseAttachmentStorage
from time_reporting.modules.registry import build_registry
from time_reporting.modules.system.backup_service import BackupService, parse_backup_filename
from time_reporting.modules.system.contracts import (
    BackupFailedError,
    BackupInfoDTO,
    BackupInProgressError,
    CreateBackup,
)
from time_reporting.modules.users.contracts import (
    CreateUser,
    EmailAlreadyExistsError,
    UserDTO,
    UserRole,
)
from time_reporting.modules.work_calendar.contracts import (
    HolidayCountryNotSupportedError,
    ImportPublicHolidays,
)
from time_reporting.seed import DEFAULT_DEMO_PASSWORD, SeedReport, seed_demo_data

_email_adapter: TypeAdapter[str] = TypeAdapter(EmailStr)


async def create_admin(bus: Bus, *, name: str, email: str, password: str) -> UserDTO:
    return await bus.execute(
        CreateUser(
            name=name,
            email=email,
            roles=frozenset({UserRole.ADMIN, UserRole.MANAGER}),
            password=password,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "seed-demo":
        return _seed_demo_command(args)
    if args.command == "import-holidays":
        return _import_holidays_command(args)
    if args.command == "backup":
        return _backup_command(args)
    if args.command == "restore":
        return _restore_command(args)
    if args.command == "prune-attachments":
        return _prune_attachments_command(args)
    return _create_admin_command(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="time-reporting", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create_admin_parser = commands.add_parser(
        "create-admin", help="create an administrator account"
    )
    create_admin_parser.add_argument("--email", required=True)
    create_admin_parser.add_argument("--name", required=True)
    create_admin_parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from the first line of stdin instead of prompting",
    )

    seed_demo_parser = commands.add_parser(
        "seed-demo",
        help="create demo users (one per role) and customers for local development; "
        "existing records are left untouched",
    )
    seed_demo_parser.add_argument(
        "--password-stdin",
        action="store_true",
        help=f"read the demo users' password from stdin instead of using {DEFAULT_DEMO_PASSWORD!r}",
    )

    import_holidays_parser = commands.add_parser(
        "import-holidays",
        help="add the configured country's public holidays for a year to the shared calendar; "
        "existing non-working days (imported or manual) are left untouched",
    )
    import_holidays_parser.add_argument("--year", required=True, type=int)

    backup_parser = commands.add_parser("backup", help="create a pg_dump backup of the database")
    backup_parser.add_argument(
        "--if-pending-migrations",
        action="store_true",
        help="only back up if the database has been migrated before and isn't already at head "
        "(used by the `migrate` service, before applying pending migrations)",
    )

    restore_parser = commands.add_parser(
        "restore", help="restore the database from a backup file (destructive; stops the app)"
    )
    restore_parser.add_argument("file", help="path to a .dump file, e.g. one from `backup`")
    restore_parser.add_argument(
        "--yes", action="store_true", help="confirm the restore; refused without this"
    )

    prune_attachments_parser = commands.add_parser(
        "prune-attachments",
        help="delete expense-attachment files on disk that no database row references "
        "(orphaned by a write whose file was saved but whose row never committed)",
    )
    prune_attachments_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be deleted without deleting anything",
    )
    return parser


def _create_admin_command(args: argparse.Namespace) -> int:
    name = str(args.name).strip()
    if not 1 <= len(name) <= 255:
        return _fail("name must be between 1 and 255 characters")
    try:
        email = _email_adapter.validate_python(args.email)
    except ValidationError:
        return _fail(f"invalid email address: {args.email}")

    password = _read_password(from_stdin=args.password_stdin)
    if password is None:
        return _fail("passwords do not match")
    if not _password_length_ok(password):
        return _fail(_PASSWORD_LENGTH_ERROR)

    try:
        admin = asyncio.run(_create_admin_in_database(name=name, email=email, password=password))
    except EmailAlreadyExistsError:
        return _fail(f"a user with email {email} already exists")
    print(f"Created administrator {admin.email} (id {admin.id})")
    return 0


def _seed_demo_command(args: argparse.Namespace) -> int:
    password = DEFAULT_DEMO_PASSWORD
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        if not _password_length_ok(password):
            return _fail(_PASSWORD_LENGTH_ERROR)

    report = asyncio.run(_seed_demo_in_database(password=password))

    for email in report.created_users:
        print(f"Created user {email}")
    for email in report.existing_users:
        print(f"Skipped user {email} (already exists)")
    for name in report.created_customers:
        print(f"Created customer {name}")
    for name in report.existing_customers:
        print(f"Skipped customer {name} (already exists)")
    for name in report.created_projects:
        print(f"Created project {name}")
    for name in report.existing_projects:
        print(f"Skipped project {name} (already exists)")
    if report.imported_holidays:
        print(f"Imported {report.imported_holidays} public holiday(s)")
    if report.created_bridge_day:
        print("Added a demo bridge day")
    if report.seeded_company_profile:
        print("Filled in the demo company profile")
    for email in report.seeded_time_entries_for:
        print(f"Booked demo time entries for {email}")
    for email in report.submitted_weeks_for:
        print(f"Submitted/approved demo timesheet weeks for {email}")
    for email in report.seeded_expense_reports_for:
        print(f"Created demo expense reports for {email}")
    if report.seeded_invoice:
        print("Sent a demo project month to billing and issued an invoice for it")
    if report.created_users:
        shown = "the one read from stdin" if args.password_stdin else DEFAULT_DEMO_PASSWORD
        print(f"New demo users sign in with password: {shown}")
    return 0


def _import_holidays_command(args: argparse.Namespace) -> int:
    try:
        added = asyncio.run(_import_holidays_in_database(year=args.year))
    except HolidayCountryNotSupportedError as exc:
        return _fail(str(exc))
    print(f"Added {added} public holiday(s) for {args.year}")
    return 0


def _backup_command(args: argparse.Namespace) -> int:
    try:
        backup = asyncio.run(
            _backup_in_database(only_if_migrations_pending=args.if_pending_migrations)
        )
    except (BackupInProgressError, BackupFailedError) as exc:
        return _fail(str(exc))
    if backup is None:
        print("Database is already at head; nothing to back up")
        return 0
    print(f"Created backup {backup.name}")
    return 0


def _restore_command(args: argparse.Namespace) -> int:
    if not args.yes:
        return _fail("refusing to restore without --yes (this replaces the database's contents)")

    path = Path(args.file)
    parsed = parse_backup_filename(path.name)
    if parsed is not None:
        _, revision = parsed
        print(f"Restoring backup from revision {revision or 'unknown'}")

    try:
        asyncio.run(_restore_in_database(path))
    except BackupFailedError as exc:
        return _fail(str(exc))
    print(f"Restored database from {path}")
    return 0


def _prune_attachments_command(args: argparse.Namespace) -> int:
    orphans = asyncio.run(_prune_attachments_in_database(dry_run=args.dry_run))
    if not orphans:
        print("No orphaned attachment files found")
        return 0
    verb = "Would delete" if args.dry_run else "Deleted"
    for key in orphans:
        print(f"{verb} {key}")
    print(f"{verb} {len(orphans)} orphaned attachment file(s)")
    return 0


async def _create_admin_in_database(*, name: str, email: str, password: str) -> UserDTO:
    return await _with_bus(lambda bus: create_admin(bus, name=name, email=email, password=password))


async def _seed_demo_in_database(*, password: str) -> SeedReport:
    return await _with_bus(lambda bus: seed_demo_data(bus, password=password))


async def _import_holidays_in_database(*, year: int) -> int:
    return await _with_bus(lambda bus: bus.execute(ImportPublicHolidays(year=year)))


async def _backup_in_database(*, only_if_migrations_pending: bool) -> BackupInfoDTO | None:
    return await _with_bus(
        lambda bus: bus.execute(CreateBackup(only_if_migrations_pending=only_if_migrations_pending))
    )


async def _restore_in_database(path: Path) -> None:
    # Deliberately not `_with_bus`: a restore replaces the whole database from the outside (a
    # `pg_restore` subprocess), independent of the app's session/engine — there is nothing for a
    # `Bus` to do here.
    await BackupService(get_settings()).restore(path)


async def _prune_attachments_in_database(*, dry_run: bool) -> tuple[str, ...]:
    referenced_keys = await _with_bus(lambda bus: bus.query(ListAttachmentStorageKeys()))
    storage = ExpenseAttachmentStorage(get_settings())
    return storage.prune_orphans(referenced_keys=referenced_keys, dry_run=dry_run)


async def _with_bus[T](action: Callable[[Bus], Awaitable[T]]) -> T:
    """Run ``action`` with a bus built the same way as for a request, then release the engine."""
    try:
        async with SessionFactory() as session:
            return await action(Bus(build_registry(), session))
    finally:
        await engine.dispose()


_PASSWORD_LENGTH_ERROR = (
    f"password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters"
)


def _password_length_ok(password: str) -> bool:
    return PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH


def _read_password(*, from_stdin: bool) -> str | None:
    """Return the password, or ``None`` if the interactive confirmation does not match."""
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Password: ")
    return password if getpass.getpass("Repeat password: ") == password else None


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
