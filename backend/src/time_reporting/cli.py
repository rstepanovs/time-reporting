"""Administrative command-line interface, installed as ``time-reporting``."""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from pydantic import EmailStr, TypeAdapter, ValidationError

from time_reporting.core.cqrs import Bus
from time_reporting.core.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from time_reporting.db.session import SessionFactory, engine
from time_reporting.modules.registry import build_registry
from time_reporting.modules.users.contracts import (
    CreateUser,
    EmailAlreadyExistsError,
    UserDTO,
    UserRole,
)

_email_adapter: TypeAdapter[str] = TypeAdapter(EmailStr)


async def create_admin(bus: Bus, *, name: str, email: str, password: str) -> UserDTO:
    return await bus.execute(
        CreateUser(name=name, email=email, role=UserRole.ADMIN, password=password)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # "create-admin" is currently the only command; the parser rejects anything else.
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
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        return _fail(
            f"password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters"
        )

    try:
        admin = asyncio.run(_create_admin_in_database(name=name, email=email, password=password))
    except EmailAlreadyExistsError:
        return _fail(f"a user with email {email} already exists")
    print(f"Created administrator {admin.email} (id {admin.id})")
    return 0


async def _create_admin_in_database(*, name: str, email: str, password: str) -> UserDTO:
    try:
        async with SessionFactory() as session:
            bus = Bus(build_registry(), session)
            return await create_admin(bus, name=name, email=email, password=password)
    finally:
        await engine.dispose()


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
