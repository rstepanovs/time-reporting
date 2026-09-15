"""Registers the work_calendar module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.work_calendar.contracts import (
    AddNonWorkingDay,
    DeleteNonWorkingDay,
    GetCalendarDays,
    ImportPublicHolidays,
    ListNonWorkingDays,
    UpdateNonWorkingDay,
)
from time_reporting.modules.work_calendar.handlers import (
    AddNonWorkingDayHandler,
    DeleteNonWorkingDayHandler,
    GetCalendarDaysHandler,
    ImportPublicHolidaysHandler,
    ListNonWorkingDaysHandler,
    UpdateNonWorkingDayHandler,
)


def register(registry: HandlerRegistry) -> None:
    registry.query(ListNonWorkingDays, ListNonWorkingDaysHandler)
    registry.query(GetCalendarDays, GetCalendarDaysHandler)

    registry.command(AddNonWorkingDay, AddNonWorkingDayHandler)
    registry.command(UpdateNonWorkingDay, UpdateNonWorkingDayHandler)
    registry.command(DeleteNonWorkingDay, DeleteNonWorkingDayHandler)
    registry.command(ImportPublicHolidays, ImportPublicHolidaysHandler)
