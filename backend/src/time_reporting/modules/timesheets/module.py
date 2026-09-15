"""Registers the timesheets module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.timesheets.contracts import (
    ApproveTimesheetWeek,
    CountTimeEntries,
    GetMonthCalendar,
    GetMonthTimeSummary,
    GetTeamMonthOverview,
    GetTimesheetWeek,
    GetWeeklyHours,
    GetYearHours,
    ListSubmittedTimesheetWeeks,
    ListTimesheetOptions,
    ReopenProjectBillingPeriod,
    ReturnTimesheetWeek,
    SaveTimesheetWeek,
    SendProjectMonthToBilling,
    SubmitTimesheetWeek,
)
from time_reporting.modules.timesheets.handlers import (
    ApproveTimesheetWeekHandler,
    CountTimeEntriesHandler,
    GetMonthCalendarHandler,
    GetMonthTimeSummaryHandler,
    GetTeamMonthOverviewHandler,
    GetTimesheetWeekHandler,
    GetWeeklyHoursHandler,
    GetYearHoursHandler,
    ListSubmittedTimesheetWeeksHandler,
    ListTimesheetOptionsHandler,
    ReopenProjectBillingPeriodHandler,
    ReturnTimesheetWeekHandler,
    SaveTimesheetWeekHandler,
    SendProjectMonthToBillingHandler,
    SubmitTimesheetWeekHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(GetTimesheetWeek, GetTimesheetWeekHandler)
    registry.query(ListTimesheetOptions, ListTimesheetOptionsHandler)
    registry.query(CountTimeEntries, CountTimeEntriesHandler)
    registry.query(GetMonthCalendar, GetMonthCalendarHandler)
    registry.query(GetYearHours, GetYearHoursHandler)
    registry.query(GetMonthTimeSummary, GetMonthTimeSummaryHandler)
    registry.query(GetWeeklyHours, GetWeeklyHoursHandler)
    registry.query(GetTeamMonthOverview, GetTeamMonthOverviewHandler)
    registry.query(ListSubmittedTimesheetWeeks, ListSubmittedTimesheetWeeksHandler)

    registry.command(SaveTimesheetWeek, SaveTimesheetWeekHandler)
    registry.command(SubmitTimesheetWeek, SubmitTimesheetWeekHandler)
    registry.command(ApproveTimesheetWeek, ApproveTimesheetWeekHandler)
    registry.command(ReturnTimesheetWeek, ReturnTimesheetWeekHandler)
    registry.command(SendProjectMonthToBilling, SendProjectMonthToBillingHandler)
    registry.command(ReopenProjectBillingPeriod, ReopenProjectBillingPeriodHandler)
