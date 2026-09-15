"""Read-side aggregation for a manager's team overview: timesheet status and hours across every
project a manager (or, for an admin's "all" view, every active project) manages, plus each
project's billing-period readiness (the "send to billing" handoff itself is a command added
alongside ``ProjectBillingPeriod``). Kept separate from ``summary.py`` (a worker's own dashboard)
and ``service.py`` (week read/write), but reuses their pure helpers.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectBillingItemsByIds,
    ListManagedProjectsWithMembers,
    ManagedProjectDTO,
)
from time_reporting.modules.timesheets.contracts import (
    BillingPeriodStatus,
    GetTeamMonthOverview,
    ProjectBillingPeriodDTO,
    TeamMemberDTO,
    TeamMemberWarning,
    TeamMemberWeekDTO,
    TeamMonthOverviewDTO,
    TeamProjectDTO,
    TeamStatusCountsDTO,
    TimesheetWeekStatus,
)
from time_reporting.modules.timesheets.models import TimeEntry
from time_reporting.modules.timesheets.repository import (
    TimeEntryRepository,
    TimesheetWeekRepository,
)
from time_reporting.modules.timesheets.summary import (
    _end_of_iso_week,
    _is_working_day,
    _month_bounds,
    _preset_of,
    _QuantityAccumulator,
    _start_of_iso_week,
)
from time_reporting.modules.users.contracts import GetUsersByIds, UserDTO
from time_reporting.modules.work_calendar.contracts import CalendarDayDTO, GetCalendarDays

_WEEK_LENGTH_DAYS = 7


class TeamOverviewService:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._entries = TimeEntryRepository(bus.session)
        self._weeks = TimesheetWeekRepository(bus.session)

    async def month_overview(self, query: GetTeamMonthOverview) -> TeamMonthOverviewDTO:
        managed = await self._bus.query(ListManagedProjectsWithMembers(manager_id=query.manager_id))

        month_first, month_last = _month_bounds(query.year, query.month)
        range_from = _start_of_iso_week(month_first)
        range_to = _end_of_iso_week(month_last)
        week_starts = _week_starts(range_from, range_to)

        project_ids = frozenset(entry.project.id for entry in managed)
        month_entries = await self._entries.list_for_projects_in_range(
            project_ids, month_first, month_last
        )
        entries_by_project_user: dict[tuple[UUID, UUID], list[TimeEntry]] = defaultdict(list)
        entries_by_project: dict[UUID, list[TimeEntry]] = defaultdict(list)
        for entry in month_entries:
            entries_by_project_user[(entry.project_id, entry.user_id)].append(entry)
            entries_by_project[entry.project_id].append(entry)

        current_member_ids_by_project = {
            entry.project.id: frozenset(member.user_id for member in entry.members)
            for entry in managed
        }
        all_current_member_ids = frozenset(
            user_id for ids in current_member_ids_by_project.values() for user_id in ids
        )
        all_user_ids = all_current_member_ids | frozenset(
            user_id for _, user_id in entries_by_project_user
        )

        users_by_id = {
            user.id: user for user in await self._bus.query(GetUsersByIds(user_ids=all_user_ids))
        }
        week_rows = await self._weeks.list_for_users_in_range(all_user_ids, range_from, range_to)
        status_by_user_week = {(row.user_id, row.week_start): row.status for row in week_rows}
        total_hours_by_user_week = await self._entries.sum_hours_by_user_week(all_user_ids)
        total_hours_by_user_month = await self._entries.sum_hours_by_user_in_range(
            all_user_ids, month_first, month_last
        )

        calendar_days = await self._bus.query(
            GetCalendarDays(date_from=range_from, date_to=range_to)
        )
        expected_hours_by_week = _expected_hours_by_week(calendar_days, week_starts)
        expected_hours_to_date = _expected_hours_to_date(
            calendar_days, month_first, month_last, query.today
        )

        team_projects = [
            await self._team_project(
                entry=entry,
                month_first=month_first,
                month_last=month_last,
                week_starts=week_starts,
                entries_for_project=entries_by_project.get(entry.project.id, []),
                entries_by_project_user=entries_by_project_user,
                users_by_id=users_by_id,
                status_by_user_week=status_by_user_week,
                total_hours_by_user_week=total_hours_by_user_week,
                total_hours_by_user_month=total_hours_by_user_month,
                expected_hours_by_week=expected_hours_by_week,
                expected_hours_to_date=expected_hours_to_date,
            )
            for entry in managed
        ]

        counts = _status_counts(all_current_member_ids, week_starts, status_by_user_week)

        return TeamMonthOverviewDTO(
            year=query.year,
            month=query.month,
            weeks=week_starts,
            projects=tuple(team_projects),
            counts=counts,
        )

    async def _team_project(
        self,
        *,
        entry: ManagedProjectDTO,
        month_first: date,
        month_last: date,
        week_starts: tuple[date, ...],
        entries_for_project: list[TimeEntry],
        entries_by_project_user: dict[tuple[UUID, UUID], list[TimeEntry]],
        users_by_id: dict[UUID, UserDTO],
        status_by_user_week: dict[tuple[UUID, date], TimesheetWeekStatus],
        total_hours_by_user_week: dict[tuple[UUID, date], Decimal],
        total_hours_by_user_month: dict[UUID, Decimal],
        expected_hours_by_week: dict[date, Decimal],
        expected_hours_to_date: Decimal,
    ) -> TeamProjectDTO:
        project = entry.project
        current_member_ids = frozenset(member.user_id for member in entry.members)
        project_user_ids = current_member_ids | frozenset(
            user_id for (project_id, user_id) in entries_by_project_user if project_id == project.id
        )

        members: list[TeamMemberDTO] = []
        for user_id in project_user_ids:
            user = users_by_id.get(user_id)
            if user is None:
                continue
            is_member = user_id in current_member_ids
            user_entries = entries_by_project_user.get((project.id, user_id), [])
            hours_by_week: dict[date, Decimal] = defaultdict(Decimal)
            for time_entry in user_entries:
                if time_entry.unit is BillingUnit.HOUR:
                    hours_by_week[_start_of_iso_week(time_entry.entry_date)] += time_entry.quantity
            project_hours = sum(hours_by_week.values(), Decimal(0))

            weeks = tuple(
                TeamMemberWeekDTO(
                    week_start=week_start,
                    iso_year=week_start.isocalendar().year,
                    iso_week=week_start.isocalendar().week,
                    status=status_by_user_week.get(
                        (user_id, week_start), TimesheetWeekStatus.DRAFT
                    ),
                    project_hours=hours_by_week.get(week_start, Decimal(0)),
                    total_hours=total_hours_by_user_week.get((user_id, week_start), Decimal(0)),
                    expected_hours=expected_hours_by_week[week_start],
                )
                for week_start in week_starts
            )

            total_hours_in_month = total_hours_by_user_month.get(user_id, Decimal(0))
            warning = None
            if is_member:
                if project_hours == 0:
                    warning = TeamMemberWarning.NO_ENTRIES
                elif total_hours_in_month < expected_hours_to_date:
                    warning = TeamMemberWarning.UNDER_EXPECTED_HOURS

            members.append(
                TeamMemberDTO(
                    user=user,
                    is_member=is_member,
                    project_hours=project_hours,
                    total_hours_in_month=total_hours_in_month,
                    expected_hours_to_date=expected_hours_to_date,
                    weeks=weeks,
                    warning=warning,
                )
            )
        members.sort(key=lambda member: (member.user.name, member.user.id))

        billing = await self._billing_period(
            project_id=project.id,
            currency=project.customer.currency,
            month_first=month_first,
            month_last=month_last,
            entries_for_project=entries_for_project,
            status_by_user_week=status_by_user_week,
        )

        return TeamProjectDTO(project=project, members=tuple(members), billing=billing)

    async def _billing_period(
        self,
        *,
        project_id: UUID,
        currency: str,
        month_first: date,
        month_last: date,
        entries_for_project: list[TimeEntry],
        status_by_user_week: dict[tuple[UUID, date], TimesheetWeekStatus],
    ) -> ProjectBillingPeriodDTO:
        scope_pairs = {
            (time_entry.user_id, _start_of_iso_week(time_entry.entry_date))
            for time_entry in entries_for_project
        }
        blocking_weeks = sum(
            1
            for pair in scope_pairs
            if status_by_user_week.get(pair, TimesheetWeekStatus.DRAFT)
            != TimesheetWeekStatus.APPROVED
        )
        weeks_in_scope = len(scope_pairs)
        status = (
            BillingPeriodStatus.READY
            if weeks_in_scope > 0 and blocking_weeks == 0
            else BillingPeriodStatus.NOT_READY
        )

        billing_item_ids = frozenset(
            time_entry.billing_item_id for time_entry in entries_for_project
        )
        items_by_id = {
            item.id: item
            for item in await self._bus.query(
                GetProjectBillingItemsByIds(billing_item_ids=billing_item_ids)
            )
        }
        accumulator = _QuantityAccumulator()
        for time_entry in entries_for_project:
            if time_entry.unit is BillingUnit.HOUR:
                accumulator.add_hours(
                    preset=_preset_of(items_by_id.get(time_entry.billing_item_id)),
                    quantity=time_entry.quantity,
                )
            elif time_entry.unit is BillingUnit.DAY:
                accumulator.add_days(time_entry.quantity)
            elif time_entry.unit is BillingUnit.AMOUNT:
                accumulator.add_amount(currency=currency, quantity=time_entry.quantity)

        return ProjectBillingPeriodDTO(
            project_id=project_id,
            period_start=month_first,
            period_end=month_last,
            status=status,
            sent_at=None,
            sent_by=None,
            blocking_weeks=blocking_weeks,
            weeks_in_scope=weeks_in_scope,
            hours=accumulator.freeze_hours(),
            per_diem_days=accumulator.days,
            expenses=accumulator.freeze_amounts(),
        )


def _week_starts(range_from: date, range_to: date) -> tuple[date, ...]:
    starts = []
    current = range_from
    while current <= range_to:
        starts.append(current)
        current += timedelta(days=_WEEK_LENGTH_DAYS)
    return tuple(starts)


def _expected_hours_by_week(
    calendar_days: tuple[CalendarDayDTO, ...], week_starts: tuple[date, ...]
) -> dict[date, Decimal]:
    daily_working_hours = get_settings().daily_working_hours
    working_days_by_week: dict[date, int] = defaultdict(int)
    for day in calendar_days:
        if _is_working_day(day):
            working_days_by_week[_start_of_iso_week(day.day)] += 1
    return {
        week_start: Decimal(working_days_by_week.get(week_start, 0)) * daily_working_hours
        for week_start in week_starts
    }


def _expected_hours_to_date(
    calendar_days: tuple[CalendarDayDTO, ...], month_first: date, month_last: date, today: date
) -> Decimal:
    daily_working_hours = get_settings().daily_working_hours
    working_days_to_date = sum(
        1
        for day in calendar_days
        if month_first <= day.day <= month_last and _is_working_day(day) and day.day <= today
    )
    return Decimal(working_days_to_date) * daily_working_hours


def _status_counts(
    member_ids: frozenset[UUID],
    week_starts: tuple[date, ...],
    status_by_user_week: dict[tuple[UUID, date], TimesheetWeekStatus],
) -> TeamStatusCountsDTO:
    tally: dict[TimesheetWeekStatus, int] = defaultdict(int)
    for user_id in member_ids:
        for week_start in week_starts:
            status = status_by_user_week.get((user_id, week_start), TimesheetWeekStatus.DRAFT)
            tally[status] += 1
    return TeamStatusCountsDTO(
        awaiting_approval=tally[TimesheetWeekStatus.SUBMITTED],
        returned=tally[TimesheetWeekStatus.RETURNED],
        not_submitted=tally[TimesheetWeekStatus.DRAFT],
        approved=tally[TimesheetWeekStatus.APPROVED],
    )
