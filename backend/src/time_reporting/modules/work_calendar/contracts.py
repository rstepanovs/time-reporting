"""Public contract of the work_calendar module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``work_calendar.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from time_reporting.core.cqrs import Command, Query

# ISO weekday numbers (Monday=1..Sunday=7) that are weekends regardless of the calendar.
WEEKEND_ISO_WEEKDAYS: frozenset[int] = frozenset({6, 7})

# The widest date range a single query may span, to keep GetCalendarDays cheap.
MAX_CALENDAR_RANGE_DAYS = 366


class NonWorkingDayKind(StrEnum):
    PUBLIC_HOLIDAY = "public_holiday"
    BRIDGE_DAY = "bridge_day"
    COMPANY_DAY_OFF = "company_day_off"


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class NonWorkingDayDTO:
    id: UUID
    day: date
    name: str
    kind: NonWorkingDayKind


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarDayDTO:
    """One calendar day, with whatever makes it non-working (if anything)."""

    day: date
    is_weekend: bool
    non_working_day: NonWorkingDayDTO | None


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class ListNonWorkingDays(Query[tuple[NonWorkingDayDTO, ...]]):
    """Non-working days ordered by date, restricted to a year when given."""

    year: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCalendarDays(Query[tuple[CalendarDayDTO, ...]]):
    """Every day from ``date_from`` to ``date_to`` (inclusive), ordered by date.

    Raises ``CalendarRangeTooWideError`` if the range spans more than
    ``MAX_CALENDAR_RANGE_DAYS`` days.
    """

    date_from: date
    date_to: date


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class AddNonWorkingDay(Command[NonWorkingDayDTO]):
    day: date
    name: str
    kind: NonWorkingDayKind


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateNonWorkingDay(Command[NonWorkingDayDTO]):
    """Partial update: fields left as ``None`` are not changed. ``kind`` is immutable."""

    non_working_day_id: UUID
    day: date | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteNonWorkingDay(Command[None]):
    non_working_day_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportPublicHolidays(Command[int]):
    """Add the public holidays of ``year`` that aren't already present, by date.

    Existing days (whether imported before or added/edited manually) are left untouched, so this
    is safe to re-run. Returns how many were added. Raises ``HolidayCountryNotSupportedError`` if
    the configured country/subdivision isn't recognized.
    """

    year: int
    # `None` for the CLI's `import-holidays` (no signed-in actor).
    actor_id: UUID | None = None


# --- Exceptions ---


class WorkCalendarError(Exception):
    """Base class for work_calendar module domain errors."""


class NonWorkingDayNotFoundError(WorkCalendarError):
    def __init__(self, non_working_day_id: UUID) -> None:
        super().__init__(f"Non-working day {non_working_day_id} not found")
        self.non_working_day_id = non_working_day_id


class NonWorkingDayAlreadyExistsError(WorkCalendarError):
    def __init__(self, day: date) -> None:
        super().__init__(f"A non-working day already exists on {day}")
        self.day = day


class HolidayCountryNotSupportedError(WorkCalendarError):
    def __init__(self, country: str, subdivision: str | None) -> None:
        detail = f"{country}/{subdivision}" if subdivision else country
        super().__init__(f"Holiday country/subdivision {detail!r} is not supported")
        self.country = country
        self.subdivision = subdivision


class CalendarRangeTooWideError(WorkCalendarError):
    def __init__(self, days: int) -> None:
        super().__init__(
            f"Requested range spans {days} days; the maximum is {MAX_CALENDAR_RANGE_DAYS}"
        )
        self.days = days
