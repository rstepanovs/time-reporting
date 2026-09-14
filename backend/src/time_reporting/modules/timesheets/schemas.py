"""HTTP request/response models of the timesheets API.

Response models mirror the shape of DTOs from ``projects.contracts`` and ``work_calendar.contracts``
(via ``from_attributes``) rather than importing those modules' own ``schemas.py`` — a module may
only reach another module's ``contracts.py``, and the HTTP response shape is this module's own to
own regardless.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from time_reporting.modules.projects.contracts import BillingItemPreset, BillingUnit
from time_reporting.modules.work_calendar.contracts import NonWorkingDayKind

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
# `gt=0`: clearing a cell is expressed by omitting it from ``changes``, not by a zero/negative
# quantity; unit-specific ceilings (24h/day, 1 day/entry) are enforced by the service.
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class NonWorkingDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day: date
    name: str
    kind: NonWorkingDayKind


class CalendarDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    is_weekend: bool
    non_working_day: NonWorkingDayResponse | None


class TimesheetCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool
    currency: str


class TimesheetProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer: TimesheetCustomerResponse
    name: str
    is_active: bool


class TimesheetBillingItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    preset: BillingItemPreset | None
    name: str
    unit: BillingUnit
    unit_rate: Decimal | None
    markup_percent: Decimal | None
    position: int
    is_active: bool


class TimesheetOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: TimesheetProjectResponse
    billing_items: list[TimesheetBillingItemResponse]


class TimeEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    quantity: Decimal
    note: str | None


class TimesheetRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: TimesheetProjectResponse
    billing_item: TimesheetBillingItemResponse
    is_open: bool
    entries: list[TimeEntryResponse]


class TimesheetUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str


class TimesheetWeekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    week_start: date
    can_edit: bool
    days: list[CalendarDayResponse]
    rows: list[TimesheetRowResponse]


class TimeEntryChangeRequest(BaseModel):
    """One cell's new value. Omit ``quantity`` (or send it as ``null``) to delete the entry."""

    model_config = ConfigDict(extra="forbid")

    billing_item_id: UUID
    date: date
    quantity: Quantity | None = None
    note: Note | None = None


class SaveTimesheetWeekRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[TimeEntryChangeRequest]
