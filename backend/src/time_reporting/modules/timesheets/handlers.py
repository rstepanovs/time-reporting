"""Command and query handlers of the timesheets module (registered in ``timesheets.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from time_reporting.core.cqrs import Bus
from time_reporting.modules.projects.contracts import (
    ListMemberProjectsWithBillingItems,
    ProjectOptionDTO,
)
from time_reporting.modules.timesheets.contracts import (
    CountTimeEntries,
    GetMonthCalendar,
    GetTimesheetWeek,
    GetYearHours,
    ListTimesheetOptions,
    MonthCalendarDTO,
    SaveTimesheetWeek,
    TimesheetWeekDTO,
    YearHoursDTO,
)
from time_reporting.modules.timesheets.repository import TimeEntryRepository
from time_reporting.modules.timesheets.service import TimesheetService
from time_reporting.modules.timesheets.summary import TimesheetSummaryService


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
