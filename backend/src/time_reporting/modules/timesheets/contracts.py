"""Public contract of the timesheets module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``timesheets.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from time_reporting.core.cqrs import Command, Query
from time_reporting.modules.projects.contracts import (
    ProjectBillingItemDTO,
    ProjectDTO,
    ProjectOptionDTO,
)
from time_reporting.modules.users.contracts import UserDTO
from time_reporting.modules.work_calendar.contracts import CalendarDayDTO

# The unit-specific ceiling a single entry's quantity may not exceed; ``amount`` entries have no
# ceiling beyond being positive.
MAX_HOUR_ENTRY_QUANTITY = Decimal("24")
MAX_DAY_ENTRY_QUANTITY = Decimal("1")
# The combined quantity of all `hour`-unit entries a user may book on a single date.
MAX_DAILY_HOURS = Decimal("24")
# The widest range `GetWeeklyHours` may cover.
MAX_WEEKLY_HOURS_WEEKS = 26


class TimesheetWeekStatus(StrEnum):
    """A week's place in the submit/review workflow. ``DRAFT`` is never persisted — it is the
    default for a (user, week_start) with no ``TimesheetWeek`` row."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    RETURNED = "returned"


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class TimeEntryDTO:
    date: date
    quantity: Decimal
    note: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TimesheetRowDTO:
    """One project/billing-item combination and the user's entries against it in the week.

    ``is_open`` says whether the user could still book new time here (still a member, project and
    billing item both active); a row can be listed (it has entries, or a comment) without being
    open, e.g. after the project was archived or the user was removed from it. ``comment`` is a
    per (user, week, billing item) note about the row, separate from each cell's own ``note``.
    """

    project: ProjectDTO
    billing_item: ProjectBillingItemDTO
    is_open: bool
    entries: tuple[TimeEntryDTO, ...]
    comment: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TimesheetWeekDTO:
    user: UserDTO
    week_start: date
    status: TimesheetWeekStatus
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_name: str | None
    return_comment: str | None
    # Whether the caller may change this week: they are its owner and it is draft or returned.
    can_edit: bool
    # Whether the caller may submit this week: same condition as ``can_edit``.
    can_submit: bool
    # Whether the caller may approve/return this week: an admin or project manager, not reviewing
    # their own week, and the week is submitted or approved.
    can_review: bool
    days: tuple[CalendarDayDTO, ...]
    rows: tuple[TimesheetRowDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class HoursTotalsDTO:
    """Booked ``hour``-unit quantities for a period, split by the billing item's preset.

    ``normal_hours``/``overtime_hours``/``travel_hours`` come from entries on the matching preset;
    ``other_hours`` is every other ``hour``-unit entry (custom items). ``total_hours`` is the sum
    of all four. ``day``- and ``amount``-unit entries (per diems, expenses) are not part of this —
    the worker dashboard only shows hours.
    """

    normal_hours: Decimal
    overtime_hours: Decimal
    travel_hours: Decimal
    other_hours: Decimal
    total_hours: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarDayHoursDTO:
    """One day of a month calendar: what it is (from ``work_calendar``) plus hours booked on it."""

    calendar_day: CalendarDayDTO
    in_month: bool
    is_working_day: bool
    expected_hours: Decimal
    hours: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarWeekHoursDTO:
    """One ISO week (Mon..Sun) of a month calendar; may include days outside the month."""

    week_start: date
    iso_week: int
    days: tuple[CalendarDayHoursDTO, ...]
    expected_hours: Decimal
    hours: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthCalendarDTO:
    """A month rendered as full ISO weeks (so the first/last week may spill into neighboring
    months); totals count only days that fall inside ``month``."""

    user: UserDTO
    year: int
    month: int
    weeks: tuple[CalendarWeekHoursDTO, ...]
    expected_hours: Decimal
    # Expected hours of working days up to and including ``today`` (as passed to the query).
    expected_hours_to_date: Decimal
    hours: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectHoursDTO:
    """One project's hours within a single month, for that month's breakdown. Only projects with
    any hours that month are included."""

    project: ProjectDTO
    totals: HoursTotalsDTO


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthHoursDTO:
    year: int
    month: int
    # Whether ``today`` (as passed to the query) falls inside this month.
    is_current: bool
    working_days: int
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    totals: HoursTotalsDTO
    # Sorted by customer name, then project name.
    projects: tuple[ProjectHoursDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class YearHoursDTO:
    """``year``'s hours by month, newest first: January .. ``today``'s month for the current year,
    all 12 months for a past year, none for a future one."""

    user: UserDTO
    year: int
    months: tuple[MonthHoursDTO, ...]
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    totals: HoursTotalsDTO


@dataclass(frozen=True, slots=True, kw_only=True)
class CurrencyAmountDTO:
    """A summed ``amount``-unit total in one customer currency; ``amount``-unit entries in
    different currencies are never added together."""

    currency: str
    amount: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthTimeSummaryDTO:
    """One month's booked time for the worker dashboard's "My time" card: hours split by preset
    (``hours``, as in ``HoursTotalsDTO``), plus the benefits that aren't hours — ``day``-unit
    entries (per diems) as ``per_diem_days`` and ``amount``-unit entries (expenses) summed per
    currency as ``expenses``.
    """

    user: UserDTO
    year: int
    month: int
    # Whether ``today`` (as passed to the query) falls inside this month.
    is_current: bool
    working_days: int
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    hours: HoursTotalsDTO
    per_diem_days: Decimal
    expenses: tuple[CurrencyAmountDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class WeekHoursDTO:
    """One ISO week's booked ``hour``-unit totals, for the dashboard's hours-per-week chart."""

    week_start: date
    iso_year: int
    iso_week: int
    # Whether this is the week containing ``today`` (as passed to the query).
    is_current: bool
    expected_hours: Decimal
    expected_hours_to_date: Decimal
    totals: HoursTotalsDTO


@dataclass(frozen=True, slots=True, kw_only=True)
class WeeklyHoursDTO:
    """``weeks`` consecutive ISO weeks ending with the week containing ``today``, oldest first, for
    the dashboard's hours-per-week chart, plus each project's hour totals over that same range
    (sorted by customer name, then project name; only projects with any hours in range) for the
    accompanying per-project table.
    """

    user: UserDTO
    weeks: tuple[WeekHoursDTO, ...]
    projects: tuple[ProjectHoursDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class TimesheetWeekSummaryDTO:
    """One submitted week, for a manager's approvals list."""

    user: UserDTO
    week_start: date
    status: TimesheetWeekStatus
    submitted_at: datetime
    total_hours: Decimal


class BillingPeriodStatus(StrEnum):
    """A project's month, for the manager's billing handoff. No ``ProjectBillingPeriod`` row yet
    (added alongside ``SendProjectMonthToBilling``) means ``NOT_READY``/``READY``; ``SENT`` is set
    once one exists."""

    NOT_READY = "not_ready"
    READY = "ready"
    SENT = "sent"


class TeamMemberWarning(StrEnum):
    """A non-blocking flag on a team member's month, for the manager to look into — not
    necessarily a problem (could be vacation)."""

    NO_ENTRIES = "no_entries"
    UNDER_EXPECTED_HOURS = "under_expected_hours"


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamMemberWeekDTO:
    """One ISO week of one team member's month, for the team overview's week-by-week grid.

    ``project_hours`` is this project's ``hour``-unit total for the week, clipped to the days that
    fall inside the overview's month (so a week straddling two months only counts one month's
    days); ``total_hours`` is the member's ``hour``-unit total across *all* projects for the whole
    week (not clipped), matching what the timesheet week page itself would show.
    """

    week_start: date
    iso_year: int
    iso_week: int
    status: TimesheetWeekStatus
    project_hours: Decimal
    total_hours: Decimal
    expected_hours: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamMemberDTO:
    """One project's member, for the team overview. ``is_member`` is ``False`` for someone who
    booked time on the project this month but was since removed from it — still shown (read-only
    history), just not counted as current staff."""

    user: UserDTO
    is_member: bool
    # This project's hour total for the month (sum of ``weeks[*].project_hours``).
    project_hours: Decimal
    # This member's hour total across all projects for the calendar month (not clipped to weeks).
    total_hours_in_month: Decimal
    expected_hours_to_date: Decimal
    weeks: tuple[TeamMemberWeekDTO, ...]
    warning: TeamMemberWarning | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectBillingPeriodDTO:
    """One project's calendar month, and whether it is ready to be sent to billing.

    ``weeks_in_scope`` is the number of distinct (user, ISO week) pairs with at least one entry on
    this project dated inside the month; ``blocking_weeks`` is how many of those aren't
    ``approved`` yet. ``READY`` requires at least one week in scope and none blocking.
    """

    project_id: UUID
    period_start: date
    period_end: date
    status: BillingPeriodStatus
    sent_at: datetime | None
    sent_by: UserDTO | None
    blocking_weeks: int
    weeks_in_scope: int
    hours: HoursTotalsDTO
    per_diem_days: Decimal
    expenses: tuple[CurrencyAmountDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamProjectDTO:
    """One managed project's month, for the team overview: its members and billing readiness."""

    project: ProjectDTO
    members: tuple[TeamMemberDTO, ...]
    billing: ProjectBillingPeriodDTO


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamStatusCountsDTO:
    """How many distinct (member, ISO week) pairs across every managed project's current members
    are in each status, for the dashboard's "Timesheets" card. A pair with no ``TimesheetWeek`` row
    counts as ``not_submitted``, matching ``draft``."""

    awaiting_approval: int
    returned: int
    not_submitted: int
    approved: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TeamMonthOverviewDTO:
    """A manager's team for one calendar month: every project they manage (or, for
    ``manager_id=None``, every active project), each with its members and billing status.

    ``weeks`` are the ISO week start dates spanning the month (its first/last week may spill into
    neighboring months), shared as the grid's columns across all projects.
    """

    year: int
    month: int
    weeks: tuple[date, ...]
    projects: tuple[TeamProjectDTO, ...]
    counts: TeamStatusCountsDTO


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetTimesheetWeek(Query[TimesheetWeekDTO]):
    """Raises ``UserNotFoundError`` (users module) if ``user_id`` doesn't exist, or
    ``WeekStartNotMondayError`` if ``week_start`` isn't a Monday."""

    user_id: UUID
    week_start: date
    viewer_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListTimesheetOptions(Query[tuple[ProjectOptionDTO, ...]]):
    """The projects/billing items ``user_id`` may currently book time against; used to build the
    "add a row" picker. Same shape as ``projects.contracts.ListMemberProjectsWithBillingItems``,
    exposed here so the HTTP layer only ever dispatches messages owned by this module."""

    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class CountTimeEntries(Query[int]):
    """Count of time entries, optionally filtered. Used by the admin module to report what a
    permanent delete of a user, project or billing item would be blocked by."""

    user_id: UUID | None = None
    project_id: UUID | None = None
    billing_item_id: UUID | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetMonthCalendar(Query[MonthCalendarDTO]):
    """``month``'s calendar for the worker dashboard, spanning full ISO weeks. ``today`` drives
    ``expected_hours_to_date`` and is supplied by the caller (the router fills in the real date) so
    the result is deterministic. Raises ``UserNotFoundError`` if ``user_id`` doesn't exist."""

    user_id: UUID
    year: int
    month: int
    today: date


@dataclass(frozen=True, slots=True, kw_only=True)
class GetYearHours(Query[YearHoursDTO]):
    """``year``'s hours by month for the worker dashboard. ``today`` is supplied by the caller,
    like ``GetMonthCalendar``. Raises ``UserNotFoundError`` if ``user_id`` doesn't exist."""

    user_id: UUID
    year: int
    today: date


@dataclass(frozen=True, slots=True, kw_only=True)
class GetMonthTimeSummary(Query[MonthTimeSummaryDTO]):
    """A single month's booked time for the worker dashboard's "My time" card. ``today`` is
    supplied by the caller (the router fills in the real date), like ``GetMonthCalendar``. Raises
    ``UserNotFoundError`` if ``user_id`` doesn't exist."""

    user_id: UUID
    year: int
    month: int
    today: date


@dataclass(frozen=True, slots=True, kw_only=True)
class GetWeeklyHours(Query[WeeklyHoursDTO]):
    """``weeks`` ISO weeks ending with ``today``'s week, for the dashboard's hours-per-week chart
    and per-project table. Raises ``UserNotFoundError`` if ``user_id`` doesn't exist, or
    ``WeekRangeOutOfBoundsError`` unless ``1 <= weeks <= MAX_WEEKLY_HOURS_WEEKS``."""

    user_id: UUID
    weeks: int
    today: date


@dataclass(frozen=True, slots=True, kw_only=True)
class ListSubmittedTimesheetWeeks(Query[tuple[TimesheetWeekSummaryDTO, ...]]):
    """Weeks awaiting review, oldest submission first, for a manager's approvals list."""


@dataclass(frozen=True, slots=True, kw_only=True)
class GetTeamMonthOverview(Query[TeamMonthOverviewDTO]):
    """A manager's team overview for ``year``/``month``. ``manager_id=None`` covers every active
    project (an admin's "all" view) rather than one manager's; ``today`` is supplied by the caller
    (the router fills in the real date), like the worker dashboard's queries."""

    manager_id: UUID | None
    year: int
    month: int
    today: date


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class TimeEntryChange:
    """One cell's new value. ``quantity=None`` deletes the entry (a no-op if there wasn't one)."""

    billing_item_id: UUID
    date: date
    quantity: Decimal | None
    note: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RowCommentChange:
    """A row's new comment. ``comment=None`` (or blank) deletes it (a no-op if there wasn't one)."""

    billing_item_id: UUID
    comment: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaveTimesheetWeek(Command[TimesheetWeekDTO]):
    """Apply ``changes``/``row_comments`` to ``user_id``'s week starting ``week_start`` and return
    the updated week.

    All changes are validated before any is applied, so a rejected batch leaves the week
    unchanged (the bus also rolls back the whole command on any exception). Raises
    ``WeekStartNotMondayError``, ``EntryDateOutsideWeekError``, ``DuplicateChangeError``,
    ``TimesheetBillingItemNotFoundError``, ``TimesheetRowClosedError``,
    ``QuantityOutOfRangeError``, ``DailyHoursExceededError`` or ``TimesheetWeekLockedError`` (the
    week is submitted or approved).
    """

    user_id: UUID
    week_start: date
    changes: tuple[TimeEntryChange, ...]
    row_comments: tuple[RowCommentChange, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmitTimesheetWeek(Command[TimesheetWeekDTO]):
    """Move ``user_id``'s week from draft/returned to submitted. Raises
    ``WeekStartNotMondayError``, ``UserNotFoundError`` or ``InvalidWeekStatusTransitionError``."""

    user_id: UUID
    week_start: date


@dataclass(frozen=True, slots=True, kw_only=True)
class ApproveTimesheetWeek(Command[TimesheetWeekDTO]):
    """Move ``user_id``'s week from submitted to approved. Raises ``WeekStartNotMondayError``,
    ``UserNotFoundError``, ``InvalidWeekStatusTransitionError`` or ``SelfReviewError`` (a project
    manager, not an admin, reviewing their own week)."""

    user_id: UUID
    week_start: date
    reviewer_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnTimesheetWeek(Command[TimesheetWeekDTO]):
    """Move ``user_id``'s week from submitted/approved back to returned, with an explanatory
    ``comment``. Raises ``WeekStartNotMondayError``, ``UserNotFoundError``,
    ``InvalidWeekStatusTransitionError``, ``SelfReviewError`` or ``ReturnCommentRequiredError``."""

    user_id: UUID
    week_start: date
    reviewer_id: UUID
    comment: str


# --- Exceptions ---


class TimesheetError(Exception):
    """Base class for timesheets module domain errors."""


class WeekStartNotMondayError(TimesheetError):
    def __init__(self, week_start: date) -> None:
        super().__init__(f"{week_start} is not a Monday")
        self.week_start = week_start


class EntryDateOutsideWeekError(TimesheetError):
    def __init__(self, entry_date: date, week_start: date) -> None:
        super().__init__(f"{entry_date} is outside the week starting {week_start}")
        self.entry_date = entry_date
        self.week_start = week_start


class DuplicateChangeError(TimesheetError):
    def __init__(self, billing_item_id: UUID, entry_date: date) -> None:
        super().__init__(f"Duplicate change for billing item {billing_item_id} on {entry_date}")
        self.billing_item_id = billing_item_id
        self.entry_date = entry_date


class TimesheetBillingItemNotFoundError(TimesheetError):
    def __init__(self, billing_item_id: UUID) -> None:
        super().__init__(f"Billing item {billing_item_id} not found")
        self.billing_item_id = billing_item_id


class TimesheetRowClosedError(TimesheetError):
    """Raised when a change targets a billing item the user can no longer book against: they are
    not (or no longer) a member of its project, or the project or billing item is archived."""

    def __init__(self, billing_item_id: UUID) -> None:
        super().__init__(f"Billing item {billing_item_id} is not open for this user")
        self.billing_item_id = billing_item_id


class QuantityOutOfRangeError(TimesheetError):
    def __init__(self, billing_item_id: UUID, entry_date: date, quantity: Decimal) -> None:
        super().__init__(
            f"Quantity {quantity} on {entry_date} is out of range for billing item "
            f"{billing_item_id}"
        )
        self.billing_item_id = billing_item_id
        self.entry_date = entry_date
        self.quantity = quantity


class DailyHoursExceededError(TimesheetError):
    def __init__(self, entry_date: date, total_hours: Decimal) -> None:
        super().__init__(
            f"Total hours on {entry_date} would be {total_hours}, more than "
            f"{MAX_DAILY_HOURS} allowed per day"
        )
        self.entry_date = entry_date
        self.total_hours = total_hours


class WeekRangeOutOfBoundsError(TimesheetError):
    def __init__(self, weeks: int) -> None:
        super().__init__(f"weeks must be between 1 and {MAX_WEEKLY_HOURS_WEEKS}, got {weeks}")
        self.weeks = weeks


class TimesheetWeekLockedError(TimesheetError):
    """Raised by ``SaveTimesheetWeek`` when the week is submitted or approved."""

    def __init__(self, week_start: date, status: TimesheetWeekStatus) -> None:
        super().__init__(f"Week starting {week_start} is {status} and cannot be edited")
        self.week_start = week_start
        self.status = status


class InvalidWeekStatusTransitionError(TimesheetError):
    def __init__(self, week_start: date, status: TimesheetWeekStatus, action: str) -> None:
        super().__init__(f"Cannot {action} week starting {week_start}: it is {status}")
        self.week_start = week_start
        self.status = status
        self.action = action


class SelfReviewError(TimesheetError):
    def __init__(self) -> None:
        super().__init__("A project manager cannot approve or return their own week")


class ReturnCommentRequiredError(TimesheetError):
    def __init__(self) -> None:
        super().__init__("Returning a week requires a non-empty comment")
