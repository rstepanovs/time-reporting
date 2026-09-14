"""Public contract of the timesheets module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``timesheets.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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
    billing item both active); a row can be listed (it has entries) without being open, e.g. after
    the project was archived or the user was removed from it.
    """

    project: ProjectDTO
    billing_item: ProjectBillingItemDTO
    is_open: bool
    entries: tuple[TimeEntryDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class TimesheetWeekDTO:
    user: UserDTO
    week_start: date
    # Whether the caller may change this week (they are its owner); admins/managers viewing
    # someone else's week get the same data with ``can_edit=False``.
    can_edit: bool
    days: tuple[CalendarDayDTO, ...]
    rows: tuple[TimesheetRowDTO, ...]


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


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class TimeEntryChange:
    """One cell's new value. ``quantity=None`` deletes the entry (a no-op if there wasn't one)."""

    billing_item_id: UUID
    date: date
    quantity: Decimal | None
    note: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaveTimesheetWeek(Command[TimesheetWeekDTO]):
    """Apply ``changes`` to ``user_id``'s week starting ``week_start`` and return the updated week.

    All changes are validated before any is applied, so a rejected batch leaves the week
    unchanged (the bus also rolls back the whole command on any exception). Raises
    ``WeekStartNotMondayError``, ``EntryDateOutsideWeekError``, ``DuplicateChangeError``,
    ``TimesheetBillingItemNotFoundError``, ``TimesheetRowClosedError``,
    ``QuantityOutOfRangeError`` or ``DailyHoursExceededError``.
    """

    user_id: UUID
    week_start: date
    changes: tuple[TimeEntryChange, ...]


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
