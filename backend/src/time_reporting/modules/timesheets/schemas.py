"""HTTP request/response models of the timesheets API.

Response models mirror the shape of DTOs from ``projects.contracts`` and ``work_calendar.contracts``
(via ``from_attributes``) rather than importing those modules' own ``schemas.py`` — a module may
only reach another module's ``contracts.py``, and the HTTP response shape is this module's own to
own regardless.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from time_reporting.modules.projects.contracts import BillingItemPreset, BillingUnit
from time_reporting.modules.timesheets.contracts import (
    BillingPeriodStatus,
    TeamMemberWarning,
    TimesheetWeekStatus,
)
from time_reporting.modules.work_calendar.contracts import NonWorkingDayKind

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
# `gt=0`: clearing a cell is expressed by omitting it from ``changes``, not by a zero/negative
# quantity; unit-specific ceilings (24h/day, 1 day/entry) are enforced by the service.
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
# A row's comment; clearing it (deleting the row) is expressed by omitting it from
# ``row_comments`` or sending it as ``null``, like ``TimeEntryChangeRequest.quantity``.
RowComment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
# A non-blank explanation, required when returning a week to its owner for corrections.
ReturnComment = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
]


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
    normal_working_hours: Decimal


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
    comment: str | None
    locked_dates: list[date] = []


class TimesheetUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str


class TimesheetWeekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    week_start: date
    status: TimesheetWeekStatus
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_name: str | None
    return_comment: str | None
    can_edit: bool
    can_submit: bool
    can_review: bool
    days: list[CalendarDayResponse]
    rows: list[TimesheetRowResponse]


class TimesheetWeekSummaryResponse(BaseModel):
    """One row of the manager's approvals list (``GET /timesheets/submissions``)."""

    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    week_start: date
    status: TimesheetWeekStatus
    submitted_at: datetime
    total_hours: Decimal


class TimeEntryChangeRequest(BaseModel):
    """One cell's new value. Omit ``quantity`` (or send it as ``null``) to delete the entry."""

    model_config = ConfigDict(extra="forbid")

    billing_item_id: UUID
    date: date
    quantity: Quantity | None = None
    note: Note | None = None


class RowCommentChangeRequest(BaseModel):
    """A row's new comment. Omit ``comment`` (or send it as ``null``) to delete it — the row's
    other fields (deleting every cell) usually accompany this when deleting the whole row."""

    model_config = ConfigDict(extra="forbid")

    billing_item_id: UUID
    comment: RowComment | None = None


class SaveTimesheetWeekRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[TimeEntryChangeRequest]
    row_comments: list[RowCommentChangeRequest] = []


class ReturnTimesheetWeekRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: ReturnComment


class HoursTotalsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    normal_hours: Decimal
    overtime_hours: Decimal
    travel_hours: Decimal
    other_hours: Decimal
    total_hours: Decimal


class CalendarDayHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calendar_day: CalendarDayResponse
    in_month: bool
    is_working_day: bool
    expected_hours: Decimal
    hours: Decimal


class CalendarWeekHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    week_start: date
    iso_week: int
    days: list[CalendarDayHoursResponse]
    expected_hours: Decimal
    hours: Decimal


class MonthCalendarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    year: int
    month: int
    weeks: list[CalendarWeekHoursResponse]
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    hours: Decimal


class ProjectHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: TimesheetProjectResponse
    totals: HoursTotalsResponse


class MonthHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    is_current: bool
    working_days: int
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    totals: HoursTotalsResponse
    projects: list[ProjectHoursResponse]


class YearHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    year: int
    months: list[MonthHoursResponse]
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    totals: HoursTotalsResponse


class CurrencyAmountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    amount: Decimal


class MonthTimeSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    year: int
    month: int
    is_current: bool
    working_days: int
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    hours: HoursTotalsResponse
    per_diem_days: Decimal
    expenses: list[CurrencyAmountResponse]


class WeekHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    week_start: date
    iso_year: int
    iso_week: int
    is_current: bool
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    totals: HoursTotalsResponse


class WeeklyHoursResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    weeks: list[WeekHoursResponse]
    projects: list[ProjectHoursResponse]


class TeamMemberWeekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    week_start: date
    iso_year: int
    iso_week: int
    status: TimesheetWeekStatus
    project_hours: Decimal
    total_hours: Decimal
    expected_hours: Decimal


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: TimesheetUserResponse
    is_member: bool
    project_hours: Decimal
    total_hours_in_month: Decimal
    expected_hours_to_date: Decimal
    weeks: list[TeamMemberWeekResponse]
    warning: TeamMemberWarning | None


class ProjectBillingPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    period_start: date
    period_end: date
    status: BillingPeriodStatus
    sent_at: datetime | None
    sent_by: TimesheetUserResponse | None
    blocking_weeks: int
    blocking_reports: int
    weeks_in_scope: int
    hours: HoursTotalsResponse
    per_diem_days: Decimal
    expenses: list[CurrencyAmountResponse]


class TeamProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: TimesheetProjectResponse
    members: list[TeamMemberResponse]
    billing: ProjectBillingPeriodResponse


class BillingPeriodListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    project_name: str
    customer_name: str
    period_start: date
    period_end: date
    sent_at: datetime
    sent_by_id: UUID
    sent_by_name: str
    invoice_id: UUID | None


class BillingPeriodPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[BillingPeriodListItemResponse]
    total: int
    limit: int
    offset: int


class TeamStatusCountsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    awaiting_approval: int
    returned: int
    not_submitted: int
    approved: int


class TeamMonthOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    weeks: list[date]
    projects: list[TeamProjectResponse]
    counts: TeamStatusCountsResponse


class SendProjectMonthToBillingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    year: Annotated[int, Field(ge=2000, le=2100)]
    month: Annotated[int, Field(ge=1, le=12)]
