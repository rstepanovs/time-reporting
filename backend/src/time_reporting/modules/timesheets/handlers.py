"""Command and query handlers of the timesheets module (registered in ``timesheets.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    BillingUnit,
    GetProjectsByIds,
    ListManagedProjectsWithMembers,
    ListMemberProjectsWithBillingItems,
    ListProjects,
    ProjectOptionDTO,
)
from time_reporting.modules.timesheets.billing import BillingService
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    BillingPeriodListItemDTO,
    BillingPeriodPageDTO,
    CountTimeEntries,
    GetMonthCalendar,
    GetMonthTimeSummary,
    GetTeamMonthOverview,
    GetTimesheetWeek,
    GetWeeklyHours,
    GetYearHours,
    ListBillingPeriods,
    ListSubmittedTimesheetWeeks,
    ListTimesheetOptions,
    MonthCalendarDTO,
    MonthTimeSummaryDTO,
    ProjectBillingPeriodDTO,
    ReopenProjectBillingPeriod,
    ReturnTimesheetWeek,
    SaveTimesheetWeek,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
    TeamMonthOverviewDTO,
    TimesheetWeekDTO,
    TimesheetWeekStatus,
    TimesheetWeekSummaryDTO,
    WeeklyHoursDTO,
    YearHoursDTO,
)
from time_reporting.modules.timesheets.models import TimesheetWeek
from time_reporting.modules.timesheets.repository import (
    ProjectBillingPeriodRepository,
    TimeEntryRepository,
    TimesheetWeekRepository,
)
from time_reporting.modules.timesheets.service import TimesheetService
from time_reporting.modules.timesheets.summary import TimesheetSummaryService, _start_of_iso_week
from time_reporting.modules.timesheets.team import TeamOverviewService
from time_reporting.modules.users.contracts import GetUsersByIds

# Large enough that no customer plausibly has more active+archived projects than this; resolving
# `ListBillingPeriods.customer_id` only needs every matching project's id, not a further page.
_CUSTOMER_PROJECTS_LIMIT = 10_000


class GetTimesheetWeekHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetService(bus)

    async def handle(self, query: GetTimesheetWeek) -> TimesheetWeekDTO:
        return await self._service.get_week(
            user_id=query.user_id, week_start=query.week_start, viewer_id=query.viewer_id
        )


class ListTimesheetOptionsHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus

    async def handle(self, query: ListTimesheetOptions) -> tuple[ProjectOptionDTO, ...]:
        # `amount` items are claimed only through the expenses module now — see expenses/CLAUDE.md.
        return await self._bus.query(
            ListMemberProjectsWithBillingItems(
                user_id=query.user_id, units=frozenset({BillingUnit.HOUR, BillingUnit.DAY})
            )
        )


class CountTimeEntriesHandler:
    def __init__(self, bus: Bus) -> None:
        self._entries = TimeEntryRepository(bus.session)

    async def handle(self, query: CountTimeEntries) -> int:
        return await self._entries.count(
            user_id=query.user_id,
            project_id=query.project_id,
            billing_item_id=query.billing_item_id,
        )


class SaveTimesheetWeekHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetService(bus)

    async def handle(self, command: SaveTimesheetWeek) -> TimesheetWeekDTO:
        return await self._service.save_week(command)


class GetMonthCalendarHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetSummaryService(bus)

    async def handle(self, query: GetMonthCalendar) -> MonthCalendarDTO:
        return await self._service.month_calendar(
            user_id=query.user_id, year=query.year, month=query.month, today=query.today
        )


class GetYearHoursHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetSummaryService(bus)

    async def handle(self, query: GetYearHours) -> YearHoursDTO:
        return await self._service.year_hours(
            user_id=query.user_id, year=query.year, today=query.today
        )


class GetMonthTimeSummaryHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetSummaryService(bus)

    async def handle(self, query: GetMonthTimeSummary) -> MonthTimeSummaryDTO:
        return await self._service.month_time_summary(
            user_id=query.user_id, year=query.year, month=query.month, today=query.today
        )


class GetWeeklyHoursHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetSummaryService(bus)

    async def handle(self, query: GetWeeklyHours) -> WeeklyHoursDTO:
        return await self._service.weekly_hours(
            user_id=query.user_id, weeks=query.weeks, today=query.today
        )


class SubmitTimesheetWeekHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetService(bus)

    async def handle(self, command: SubmitTimesheetWeek) -> TimesheetWeekDTO:
        return await self._service.submit_week(command)


class ApproveTimesheetWeekHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetService(bus)

    async def handle(self, command: ApproveTimesheetWeek) -> TimesheetWeekDTO:
        return await self._service.approve_week(command)


class ReturnTimesheetWeekHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TimesheetService(bus)

    async def handle(self, command: ReturnTimesheetWeek) -> TimesheetWeekDTO:
        return await self._service.return_week(command)


class GetTeamMonthOverviewHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = TeamOverviewService(bus)

    async def handle(self, query: GetTeamMonthOverview) -> TeamMonthOverviewDTO:
        return await self._service.month_overview(query)


class SendProjectMonthToBillingHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = BillingService(bus)

    async def handle(self, command: SendProjectMonthToBilling) -> ProjectBillingPeriodDTO:
        return await self._service.send_to_billing(command)


class ReopenProjectBillingPeriodHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = BillingService(bus)

    async def handle(self, command: ReopenProjectBillingPeriod) -> None:
        await self._service.reopen_period(command)


class ListBillingPeriodsHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._periods = ProjectBillingPeriodRepository(bus.session)

    async def handle(self, query: ListBillingPeriods) -> BillingPeriodPageDTO:
        project_ids = await self._resolve_project_ids(query)
        periods = await self._periods.get_page(
            project_ids=project_ids,
            month_from=query.month_from,
            month_to=query.month_to,
            limit=query.limit,
            offset=query.offset,
        )
        total = await self._periods.count(
            project_ids=project_ids, month_from=query.month_from, month_to=query.month_to
        )

        projects_by_id = {
            project.id: project
            for project in await self._bus.query(
                GetProjectsByIds(project_ids=frozenset(period.project_id for period in periods))
            )
        }
        users_by_id = {
            user.id: user
            for user in await self._bus.query(
                GetUsersByIds(user_ids=frozenset(period.sent_by_id for period in periods))
            )
        }
        items = tuple(
            BillingPeriodListItemDTO(
                project_id=period.project_id,
                project_name=projects_by_id[period.project_id].name,
                customer_name=projects_by_id[period.project_id].customer.name,
                period_start=period.period_start,
                period_end=period.period_end,
                sent_at=period.sent_at,
                sent_by_id=period.sent_by_id,
                sent_by_name=users_by_id[period.sent_by_id].name,
            )
            for period in periods
        )
        return BillingPeriodPageDTO(
            items=items, total=total, limit=query.limit, offset=query.offset
        )

    async def _resolve_project_ids(self, query: ListBillingPeriods) -> frozenset[UUID] | None:
        """``None`` means no project filter at all; an empty (but not ``None``) result means
        ``customer_id`` matched no projects, so the list is empty."""
        if query.customer_id is None:
            return frozenset({query.project_id}) if query.project_id is not None else None
        customer_projects = await self._bus.query(
            ListProjects(
                customer_id=query.customer_id,
                include_inactive=True,
                limit=_CUSTOMER_PROJECTS_LIMIT,
                offset=0,
            )
        )
        project_ids = frozenset(project.id for project in customer_projects.items)
        if query.project_id is not None:
            project_ids &= {query.project_id}
        return project_ids


class ListSubmittedTimesheetWeeksHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._weeks = TimesheetWeekRepository(bus.session)
        self._entries = TimeEntryRepository(bus.session)

    async def handle(
        self, query: ListSubmittedTimesheetWeeks
    ) -> tuple[TimesheetWeekSummaryDTO, ...]:
        week_rows = await self._weeks.list_by_status(TimesheetWeekStatus.SUBMITTED)
        if query.manager_id is not None:
            week_rows = await self._filter_by_manager(week_rows, query.manager_id)
        user_ids = frozenset(week_row.user_id for week_row in week_rows)
        users_by_id = {
            user.id: user for user in await self._bus.query(GetUsersByIds(user_ids=user_ids))
        }
        totals = await self._entries.sum_hours_by_user_week(user_ids)

        summaries: list[TimesheetWeekSummaryDTO] = []
        for week_row in week_rows:
            user = users_by_id.get(week_row.user_id)
            # A submitted week's ``submitted_at`` is always set by ``submit_week``.
            if user is None or week_row.submitted_at is None:
                continue
            summaries.append(
                TimesheetWeekSummaryDTO(
                    user=user,
                    week_start=week_row.week_start,
                    status=week_row.status,
                    submitted_at=week_row.submitted_at,
                    total_hours=totals.get((week_row.user_id, week_row.week_start), Decimal(0)),
                )
            )
        return tuple(summaries)

    async def _filter_by_manager(
        self, week_rows: Sequence[TimesheetWeek], manager_id: UUID
    ) -> Sequence[TimesheetWeek]:
        """Keep only weeks with at least one entry on a project ``manager_id`` manages."""
        managed = await self._bus.query(ListManagedProjectsWithMembers(manager_id=manager_id))
        managed_project_ids = frozenset(entry.project.id for entry in managed)
        if not managed_project_ids or not week_rows:
            return ()
        date_from = min(week_row.week_start for week_row in week_rows)
        date_to = max(week_row.week_start for week_row in week_rows) + timedelta(days=6)
        entries = await self._entries.list_for_projects_in_range(
            managed_project_ids, date_from, date_to
        )
        covered = {(entry.user_id, _start_of_iso_week(entry.entry_date)) for entry in entries}
        return [
            week_row for week_row in week_rows if (week_row.user_id, week_row.week_start) in covered
        ]
