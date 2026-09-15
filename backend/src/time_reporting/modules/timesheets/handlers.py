"""Command and query handlers of the timesheets module (registered in ``timesheets.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from decimal import Decimal

from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    ListMemberProjectsWithBillingItems,
    ProjectOptionDTO,
)
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    CountTimeEntries,
    GetMonthCalendar,
    GetMonthTimeSummary,
    GetTimesheetWeek,
    GetWeeklyHours,
    GetYearHours,
    ListSubmittedTimesheetWeeks,
    ListTimesheetOptions,
    MonthCalendarDTO,
    MonthTimeSummaryDTO,
    ReturnTimesheetWeek,
    SaveTimesheetWeek,
    SubmitTimesheetWeek,
    TimesheetWeekDTO,
    TimesheetWeekStatus,
    TimesheetWeekSummaryDTO,
    WeeklyHoursDTO,
    YearHoursDTO,
)
from time_reporting.modules.timesheets.repository import (
    TimeEntryRepository,
    TimesheetWeekRepository,
)
from time_reporting.modules.timesheets.service import TimesheetService
from time_reporting.modules.timesheets.summary import TimesheetSummaryService
from time_reporting.modules.users.contracts import GetUsersByIds


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
        return await self._bus.query(ListMemberProjectsWithBillingItems(user_id=query.user_id))


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


class ListSubmittedTimesheetWeeksHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._weeks = TimesheetWeekRepository(bus.session)
        self._entries = TimeEntryRepository(bus.session)

    async def handle(
        self, query: ListSubmittedTimesheetWeeks
    ) -> tuple[TimesheetWeekSummaryDTO, ...]:
        week_rows = await self._weeks.list_by_status(TimesheetWeekStatus.SUBMITTED)
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
