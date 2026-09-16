"""Command and query handlers of the work_calendar module (registered in ``work_calendar.module``).

Handlers translate between bus messages and the service/repository and never return ORM entities.
"""

from datetime import timedelta

from time_reporting.core.cqrs import Bus
from time_reporting.modules.audit.contracts import AuditAction, RecordAuditEvent
from time_reporting.modules.work_calendar.contracts import (
    MAX_CALENDAR_RANGE_DAYS,
    WEEKEND_ISO_WEEKDAYS,
    AddNonWorkingDay,
    CalendarDayDTO,
    CalendarRangeTooWideError,
    DeleteNonWorkingDay,
    GetCalendarDays,
    ImportPublicHolidays,
    ListNonWorkingDays,
    NonWorkingDayDTO,
    UpdateNonWorkingDay,
)
from time_reporting.modules.work_calendar.models import NonWorkingDay
from time_reporting.modules.work_calendar.repository import NonWorkingDayRepository
from time_reporting.modules.work_calendar.service import WorkCalendarService


def to_dto(non_working_day: NonWorkingDay) -> NonWorkingDayDTO:
    return NonWorkingDayDTO(
        id=non_working_day.id,
        day=non_working_day.day,
        name=non_working_day.name,
        kind=non_working_day.kind,
    )


# --- Queries ---


class _QueryHandler:
    def __init__(self, bus: Bus) -> None:
        self._non_working_days = NonWorkingDayRepository(bus.session)


class ListNonWorkingDaysHandler(_QueryHandler):
    async def handle(self, query: ListNonWorkingDays) -> tuple[NonWorkingDayDTO, ...]:
        days = await self._non_working_days.list_for_year(query.year)
        return tuple(to_dto(day) for day in days)


class GetCalendarDaysHandler(_QueryHandler):
    async def handle(self, query: GetCalendarDays) -> tuple[CalendarDayDTO, ...]:
        span = (query.date_to - query.date_from).days
        if span < 0 or span >= MAX_CALENDAR_RANGE_DAYS:
            raise CalendarRangeTooWideError(span + 1)

        non_working_days = {
            day.day: to_dto(day)
            for day in await self._non_working_days.list_in_range(query.date_from, query.date_to)
        }
        days: list[CalendarDayDTO] = []
        current = query.date_from
        while current <= query.date_to:
            days.append(
                CalendarDayDTO(
                    day=current,
                    is_weekend=current.isoweekday() in WEEKEND_ISO_WEEKDAYS,
                    non_working_day=non_working_days.get(current),
                )
            )
            current += timedelta(days=1)
        return tuple(days)


# --- Commands ---


class _CommandHandler:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._service = WorkCalendarService(bus.session)


class AddNonWorkingDayHandler(_CommandHandler):
    async def handle(self, command: AddNonWorkingDay) -> NonWorkingDayDTO:
        return to_dto(
            await self._service.add_non_working_day(
                day=command.day, name=command.name, kind=command.kind
            )
        )


class UpdateNonWorkingDayHandler(_CommandHandler):
    async def handle(self, command: UpdateNonWorkingDay) -> NonWorkingDayDTO:
        return to_dto(
            await self._service.update_non_working_day(
                command.non_working_day_id, day=command.day, name=command.name
            )
        )


class DeleteNonWorkingDayHandler(_CommandHandler):
    async def handle(self, command: DeleteNonWorkingDay) -> None:
        await self._service.delete_non_working_day(command.non_working_day_id)


class ImportPublicHolidaysHandler(_CommandHandler):
    async def handle(self, command: ImportPublicHolidays) -> int:
        added = await self._service.import_public_holidays(command.year)
        await self._bus.execute(
            RecordAuditEvent(
                actor_id=command.actor_id,
                action=AuditAction.PUBLIC_HOLIDAYS_IMPORTED,
                entity_type="calendar",
                entity_id=str(command.year),
                summary=f"Imported {added} public holiday(s) for {command.year}",
                details={"year": command.year, "added": added},
            )
        )
        return added
