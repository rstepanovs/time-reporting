"""Public contract of the users module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``users.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from time_reporting.core.cqrs import Command, Query


class UserRole(StrEnum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    WORKER = "worker"


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class UserDTO:
    id: UUID
    name: str
    email: str
    role: UserRole
    is_active: bool
    token_version: int
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class UserCredentialsDTO:
    """Data needed to authenticate a user; never expose it over HTTP."""

    id: UUID
    password_hash: str = field(repr=False)
    is_active: bool
    token_version: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UserPageDTO:
    items: tuple[UserDTO, ...]
    total: int
    limit: int
    offset: int


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetUserById(Query[UserDTO | None]):
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetUsersByIds(Query[tuple[UserDTO, ...]]):
    """Users matching ``user_ids``, ordered by name then id. Unknown ids are silently omitted."""

    user_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetUserCredentialsByEmail(Query[UserCredentialsDTO | None]):
    email: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ListUsers(Query[UserPageDTO]):
    limit: int
    offset: int
    # Case-insensitive substring match against name or email.
    search: str | None = None
    include_inactive: bool = True


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateUser(Command[UserDTO]):
    name: str
    email: str
    role: UserRole
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateUser(Command[UserDTO]):
    """Partial update on behalf of ``acting_user_id``: fields left as ``None`` are not changed."""

    user_id: UUID
    acting_user_id: UUID
    name: str | None = None
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResetUserPassword(Command[None]):
    """Set a new password and invalidate the user's issued tokens."""

    user_id: UUID
    new_password: str = field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeOwnPassword(Command[None]):
    """Like ``ResetUserPassword``, but requires the current password."""

    user_id: UUID
    current_password: str = field(repr=False)
    new_password: str = field(repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordSuccessfulLogin(Command[None]):
    """Stamp the login time and, if given, store a password hash upgraded to current parameters."""

    user_id: UUID
    rehashed_password_hash: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteUser(Command[None]):
    """Permanently delete a user. Raises ``UserInUseError`` if it is still a project member."""

    user_id: UUID
    acting_user_id: UUID


# --- Exceptions ---


class UserError(Exception):
    """Base class for users module domain errors."""


class UserNotFoundError(UserError):
    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User {user_id} not found")
        self.user_id = user_id


class EmailAlreadyExistsError(UserError):
    def __init__(self, email: str) -> None:
        super().__init__(f"A user with email {email} already exists")
        self.email = email


class SelfModificationError(UserError):
    def __init__(self) -> None:
        super().__init__("Users cannot change their own role, deactivate, or delete themselves")


class UserInUseError(UserError):
    """Raised when deleting a user blocked by data referencing it (e.g. project membership)."""

    def __init__(self, user_id: UUID) -> None:
        super().__init__(f"User {user_id} is referenced by other data and cannot be deleted")
        self.user_id = user_id


class InvalidCurrentPasswordError(UserError):
    def __init__(self) -> None:
        super().__init__("Current password is incorrect")
