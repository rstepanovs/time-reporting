"""Read-side hour aggregation for the worker dashboard: a month calendar and a year's hours by
month. Kept separate from ``service.py`` (week read/write) since this is pure aggregation over
already-saved entries — it never writes.
"""

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    BillingItemPreset,
    BillingUnit,
    GetProjectBillingItemsByIds,
    GetProjectsByIds,
    ProjectBillingItemDTO,
)
from time_reporting.modules.timesheets.contracts import (
    CalendarDayHoursDTO,
    CalendarWeekHoursDTO,
    HoursTotalsDTO,
    MonthCalendarDTO,
    MonthHoursDTO,
    ProjectHoursDTO,
    YearHoursDTO,
)
from time_reporting.modules.timesheets.repository import TimeEntryRepository
from time_reporting.modules.users.contracts import GetUserById, UserNotFoundError
from time_reporting.modules.work_calendar.contracts import CalendarDayDTO, GetCalendarDays

_WEEK_LENGTH_DAYS = 7
_MONTHS_PER_YEAR = 12


class TimesheetSummaryService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._entries = TimeEntryRepository(bus.session)

    async def month_calendar(
        self, *, user_id: UUID, year: int, month: int, today: date
    ) -> MonthCalendarDTO:
        user = await self._bus.query(GetUserById(user_id=user_id))
        if user is None:
            raise UserNotFoundError(user_id)

        month_first, month_last = _month_bounds(year, month)
        range_from = _start_of_iso_week(month_first)
        range_to = _end_of_iso_week(month_last)

        entries = await self._entries.list_for_user_in_range(user_id, range_from, range_to)
        hours_by_date: dict[date, Decimal] = defaultdict(Decimal)
        for entry in entries:
            if entry.unit is BillingUnit.HOUR:
                hours_by_date[entry.entry_date] += entry.quantity

        days = await self._bus.query(GetCalendarDays(date_from=range_from, date_to=range_to))
        days_by_date = {day.day: day for day in days}
        daily_working_hours = get_settings().daily_working_hours

        weeks: list[CalendarWeekHoursDTO] = []
        expected_hours = Decimal(0)
        expected_hours_to_date = Decimal(0)
        month_hours = Decimal(0)
        current = range_from
        while current <= range_to:
            week_days: list[CalendarDayHoursDTO] = []
            week_expected = Decimal(0)
            week_hours = Decimal(0)
            for offset in range(_WEEK_LENGTH_DAYS):
                day_date = current + timedelta(days=offset)
                calendar_day = days_by_date[day_date]
                in_month = month_first <= day_date <= month_last
                is_working_day = _is_working_day(calendar_day)
                day_expected = daily_working_hours if is_working_day else Decimal(0)
                day_hours = hours_by_date.get(day_date, Decimal(0))
                week_days.append(
                    CalendarDayHoursDTO(
                        calendar_day=calendar_day,
                        in_month=in_month,
                        is_working_day=is_working_day,
                        expected_hours=day_expected,
                        hours=day_hours,
                    )
                )
                week_expected += day_expected
                week_hours += day_hours
                if in_month:
                    expected_hours += day_expected
                    month_hours += day_hours
                    if is_working_day and day_date <= today:
                        expected_hours_to_date += day_expected
            weeks.append(
                CalendarWeekHoursDTO(
                    week_start=current,
                    iso_week=current.isocalendar().week,
                    days=tuple(week_days),
                    expected_hours=week_expected,
                    hours=week_hours,
                )
            )
            current += timedelta(days=_WEEK_LENGTH_DAYS)

        return MonthCalendarDTO(
            user=user,
            year=year,
            month=month,
            weeks=tuple(weeks),
            expected_hours=expected_hours,
            expected_hours_to_date=expected_hours_to_date,
            hours=month_hours,
        )

    async def year_hours(self, *, user_id: UUID, year: int, today: date) -> YearHoursDTO:
        user = await self._bus.query(GetUserById(user_id=user_id))
        if user is None:
            raise UserNotFoundError(user_id)

        if year < today.year:
            last_month = _MONTHS_PER_YEAR
        elif year == today.year:
            last_month = today.month
        else:
            last_month = 0
        if last_month == 0:
            return YearHoursDTO(
                user=user,
                year=year,
                months=(),
                expected_hours=Decimal(0),
                expected_hours_to_date=Decimal(0),
                totals=_HoursAccumulator().freeze(),
            )

        range_from = date(year, 1, 1)
        _, range_to = _month_bounds(year, last_month)

        days = await self._bus.query(GetCalendarDays(date_from=range_from, date_to=range_to))
        working_days_by_month: dict[int, int] = defaultdict(int)
        working_days_to_date_by_month: dict[int, int] = defaultdict(int)
        daily_working_hours = get_settings().daily_working_hours
        for day in days:
            if _is_working_day(day):
                working_days_by_month[day.day.month] += 1
                if day.day <= today:
                    working_days_to_date_by_month[day.day.month] += 1

        totals_rows = await self._entries.sum_hours_by_month_and_billing_item(
            user_id, range_from, range_to
        )
        billing_item_ids = frozenset(row.billing_item_id for row in totals_rows)
        project_ids = frozenset(row.project_id for row in totals_rows)
        items_by_id = {
            item.id: item
            for item in await self._bus.query(
                GetProjectBillingItemsByIds(billing_item_ids=billing_item_ids)
            )
        }
        projects_by_id = {
            project.id: project
            for project in await self._bus.query(GetProjectsByIds(project_ids=project_ids))
        }

        month_accumulators: dict[int, _HoursAccumulator] = defaultdict(_HoursAccumulator)
        project_accumulators: dict[tuple[int, UUID], _HoursAccumulator] = defaultdict(
            _HoursAccumulator
        )
        for row in totals_rows:
            month = row.month_start.month
            preset = _preset_of(items_by_id.get(row.billing_item_id))
            month_accumulators[month].add(preset=preset, quantity=row.total)
            if row.project_id in projects_by_id:
                project_accumulators[(month, row.project_id)].add(preset=preset, quantity=row.total)

        months: list[MonthHoursDTO] = []
        year_totals = _HoursAccumulator()
        year_expected = Decimal(0)
        year_expected_to_date = Decimal(0)
        for month in range(last_month, 0, -1):
            working_days = working_days_by_month.get(month, 0)
            expected_hours = Decimal(working_days) * daily_working_hours
            is_current = year == today.year and month == today.month
            if is_current:
                working_days_to_date = working_days_to_date_by_month.get(month, 0)
                expected_hours_to_date = Decimal(working_days_to_date) * daily_working_hours
            else:
                expected_hours_to_date = expected_hours

            projects = sorted(
                (
                    ProjectHoursDTO(project=projects_by_id[project_id], totals=acc.freeze())
                    for (m, project_id), acc in project_accumulators.items()
                    if m == month
                ),
                key=_project_sort_key,
            )

            totals = month_accumulators[month].freeze()
            months.append(
                MonthHoursDTO(
                    year=year,
                    month=month,
                    is_current=is_current,
                    working_days=working_days,
                    expected_hours=expected_hours,
                    expected_hours_to_date=expected_hours_to_date,
                    totals=totals,
                    projects=tuple(projects),
                )
            )
            year_totals.merge(month_accumulators[month])
            year_expected += expected_hours
            year_expected_to_date += expected_hours_to_date

        return YearHoursDTO(
            user=user,
            year=year,
            months=tuple(months),
            expected_hours=year_expected,
            expected_hours_to_date=year_expected_to_date,
            totals=year_totals.freeze(),
        )


def _project_sort_key(item: ProjectHoursDTO) -> tuple[str, str]:
    return (item.project.customer.name, item.project.name)


def _preset_of(billing_item: ProjectBillingItemDTO | None) -> BillingItemPreset | None:
    return billing_item.preset if billing_item is not None else None


@dataclass
class _HoursAccumulator:
    normal_hours: Decimal = Decimal(0)
    overtime_hours: Decimal = Decimal(0)
    travel_hours: Decimal = Decimal(0)
    other_hours: Decimal = Decimal(0)

    def add(self, *, preset: BillingItemPreset | None, quantity: Decimal) -> None:
        if preset is BillingItemPreset.NORMAL_HOURS:
            self.normal_hours += quantity
        elif preset is BillingItemPreset.OVERTIME_HOURS:
            self.overtime_hours += quantity
        elif preset is BillingItemPreset.TRAVEL_TIME:
            self.travel_hours += quantity
        else:
            self.other_hours += quantity

    def merge(self, other: "_HoursAccumulator") -> None:
        self.normal_hours += other.normal_hours
        self.overtime_hours += other.overtime_hours
        self.travel_hours += other.travel_hours
        self.other_hours += other.other_hours

    def freeze(self) -> HoursTotalsDTO:
        total_hours = self.normal_hours + self.overtime_hours + self.travel_hours + self.other_hours
        return HoursTotalsDTO(
            normal_hours=self.normal_hours,
            overtime_hours=self.overtime_hours,
            travel_hours=self.travel_hours,
            other_hours=self.other_hours,
            total_hours=total_hours,
        )


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    return first, date(year, month, last_day)


def _start_of_iso_week(day: date) -> date:
    return day - timedelta(days=day.isoweekday() - 1)


def _end_of_iso_week(day: date) -> date:
    return day + timedelta(days=_WEEK_LENGTH_DAYS - day.isoweekday())


def _is_working_day(day: CalendarDayDTO) -> bool:
    return not day.is_weekend and day.non_working_day is None
