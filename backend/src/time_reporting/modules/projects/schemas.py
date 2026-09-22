"""HTTP request/response models of the projects API."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from time_reporting.modules.projects.contracts import BillingItemPreset, BillingUnit
from time_reporting.modules.users.contracts import UserRole

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
# Matches the ``project_billing_items`` check constraints; the service checks the value against
# the item's unit (a rate for an ``amount`` item, say), which is a business rule, not a shape one.
Rate = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Markup = Annotated[Decimal, Field(ge=0, le=1000, max_digits=6, decimal_places=2)]
# Matches the ``projects`` check constraint (``0 < normal_working_hours <= 24``).
NormalWorkingHours = Annotated[Decimal, Field(gt=0, le=24, max_digits=4, decimal_places=2)]


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    name: ShortText
    description: Description | None = None
    normal_working_hours: NormalWorkingHours = Decimal("8.00")
    is_internal: bool = False
    manager_id: UUID | None = None


class ProjectUpdateRequest(BaseModel):
    """Partial update: omitted fields are left unchanged.

    ``customer_id`` is immutable and not part of this request. ``null`` clears ``description`` and
    ``manager_id``; it is rejected for ``name``, ``is_active``, ``normal_working_hours`` and
    ``is_internal``.
    """

    model_config = ConfigDict(extra="forbid")

    name: ShortText | None = None
    description: Description | None = None
    is_active: bool | None = None
    normal_working_hours: NormalWorkingHours | None = None
    is_internal: bool | None = None
    manager_id: UUID | None = None

    @model_validator(mode="after")
    def _reject_null_for_required_fields(self) -> Self:
        nulls = [
            name
            for name in ("name", "is_active", "normal_working_hours", "is_internal")
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if nulls:
            raise ValueError(f"These fields cannot be null: {', '.join(nulls)}")
        return self


class ProjectMemberAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID


class BillingItemCreateRequest(BaseModel):
    """A custom item; ``preset`` is not accepted here — only ``AddProjectBillingItem`` sets it,
    and only for the six items a project is created with."""

    model_config = ConfigDict(extra="forbid")

    name: ShortText
    unit: BillingUnit
    description: Description | None = None
    unit_rate: Rate | None = None
    markup_percent: Markup | None = None


class BillingItemUpdateRequest(BaseModel):
    """Partial update: omitted fields are left unchanged.

    ``unit`` and ``preset`` are immutable and not part of this request. ``null`` clears
    ``description``, ``unit_rate`` and ``markup_percent``; it is rejected for ``name`` and
    ``is_active``.
    """

    model_config = ConfigDict(extra="forbid")

    name: ShortText | None = None
    description: Description | None = None
    unit_rate: Rate | None = None
    markup_percent: Markup | None = None
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


class ProjectCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool
    # ISO 4217 code; billing item rates below are in this currency.
    currency: str


class ProjectManagerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    is_active: bool


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer: ProjectCustomerResponse
    name: str
    description: str | None
    is_active: bool
    normal_working_hours: Decimal
    is_internal: bool
    manager: ProjectManagerResponse | None
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
    roles: frozenset[UserRole]
    is_active: bool
    added_at: datetime


class ProjectBillingItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    preset: BillingItemPreset | None
    name: str
    description: str | None
    unit: BillingUnit
    unit_rate: Decimal | None
    markup_percent: Decimal | None
    position: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
