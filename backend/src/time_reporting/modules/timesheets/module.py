"""Registers the timesheets module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.timesheets.contracts import (
    CountTimeEntries,
    GetMonthCalendar,
    GetMonthTimeSummary,
    GetTimesheetWeek,
    GetWeeklyHours,
    GetYearHours,
    ListTimesheetOptions,
    SaveTimesheetWeek,
)
from time_reporting.modules.timesheets.handlers import (
    CountTimeEntriesHandler,
    GetMonthCalendarHandler,
    GetMonthTimeSummaryHandler,
    GetTimesheetWeekHandler,
    GetWeeklyHoursHandler,
    GetYearHoursHandler,
    ListTimesheetOptionsHandler,
    SaveTimesheetWeekHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetTimesheetWeek, GetTimesheetWeekHandler)
    registry.query(ListTimesheetOptions, ListTimesheetOptionsHandler)
    registry.query(CountTimeEntries, CountTimeEntriesHandler)
    registry.query(GetMonthCalendar, GetMonthCalendarHandler)
    registry.query(GetYearHours, GetYearHoursHandler)
    registry.query(GetMonthTimeSummary, GetMonthTimeSummaryHandler)
    registry.query(GetWeeklyHours, GetWeeklyHoursHandler)

    registry.command(SaveTimesheetWeek, SaveTimesheetWeekHandler)
