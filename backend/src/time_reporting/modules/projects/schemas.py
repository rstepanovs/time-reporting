"""HTTP request/response models of the projects API."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from time_reporting.modules.users.contracts import UserRole

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    name: ShortText
    description: Description | None = None


class ProjectUpdateRequest(BaseModel):
    """Partial update: omitted fields are left unchanged.

    ``customer_id`` is immutable and not part of this request. ``null`` clears ``description``; it
    is rejected for ``name`` and ``is_active``.
    """

    model_config = ConfigDict(extra="forbid")

    name: ShortText | None = None
    description: Description | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _reject_null_for_required_fields(self) -> Self:
        nulls = [
            name
            for name in ("name", "is_active")
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if nulls:
            raise ValueError(f"These fields cannot be null: {', '.join(nulls)}")
        return self


class ProjectMemberAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID


class ProjectCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer: ProjectCustomerResponse
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    name: str
    email: str
    role: UserRole
    is_active: bool
    added_at: datetime
