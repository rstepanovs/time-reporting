"""HTTP request/response models of the users API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from time_reporting.core.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from time_reporting.modules.users.contracts import UserRole

UserName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: UserName
    email: EmailStr
    roles: frozenset[UserRole]
    password: NewPassword


class UserUpdateRequest(BaseModel):
    """Partial update: omitted (or null) fields are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: UserName | None = None
    email: EmailStr | None = None
    roles: frozenset[UserRole] | None = None
    is_active: bool | None = None


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[str, Field(max_length=PASSWORD_MAX_LENGTH)]
    new_password: NewPassword


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: NewPassword


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    roles: frozenset[UserRole]
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[UserResponse]
    total: int
    limit: int
    offset: int


class UserSummaryResponse(BaseModel):
    """Minimal user fields for pickers (e.g. the project member directory)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    roles: frozenset[UserRole]
