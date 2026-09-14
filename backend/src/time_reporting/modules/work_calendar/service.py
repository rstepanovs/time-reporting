"""Work calendar domain logic on ORM entities.

Changes are flushed through the repository; the bus commits.
"""

from datetime import date
from uuid import UUID

import holidays
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.core.config import get_settings
from time_reporting.modules.work_calendar.contracts import (
    HolidayCountryNotSupportedError,
    NonWorkingDayAlreadyExistsError,
    NonWorkingDayKind,
    NonWorkingDayNotFoundError,
)
from time_reporting.modules.work_calendar.models import NonWorkingDay
from time_reporting.modules.work_calendar.repository import NonWorkingDayRepository


class WorkCalendarService:
    def __init__(self, session: AsyncSession) -> None:
        self._non_working_days = NonWorkingDayRepository(session)

    async def get_non_working_day(self, non_working_day_id: UUID) -> NonWorkingDay:
        non_working_day = await self._non_working_days.get_by_id(non_working_day_id)
        if non_working_day is None:
            raise NonWorkingDayNotFoundError(non_working_day_id)
        return non_working_day

    async def add_non_working_day(
        self, *, day: date, name: str, kind: NonWorkingDayKind
    ) -> NonWorkingDay:
        await self._ensure_date_available(day)
        non_working_day = NonWorkingDay(day=day, name=name, kind=kind)
        await self._non_working_days.save(non_working_day)
        return non_working_day

    async def update_non_working_day(
        self, non_working_day_id: UUID, *, day: date | None, name: str | None
    ) -> NonWorkingDay:
        non_working_day = await self.get_non_working_day(non_working_day_id)
        if day is not None and day != non_working_day.day:
            await self._ensure_date_available(day)
            non_working_day.day = day
        if name is not None:
            non_working_day.name = name
        await self._non_working_days.save(non_working_day)
        return non_working_day

    async def _ensure_date_available(self, day: date) -> None:
        if await self._non_working_days.get_by_day(day) is not None:
            raise NonWorkingDayAlreadyExistsError(day)

    async def delete_non_working_day(self, non_working_day_id: UUID) -> None:
        await self._non_working_days.delete(await self.get_non_working_day(non_working_day_id))

    async def import_public_holidays(self, year: int) -> int:
        """Add ``year``'s public holidays that aren't already present (matched by date)."""
        settings = get_settings()
        try:
            year_holidays = holidays.country_holidays(
                settings.holiday_country,
                # An empty string (e.g. from an unset .env value) means "no subdivision", same as
                # None.
                subdiv=settings.holiday_subdivision or None,
                years=year,
                language="en_US",
            )
        except NotImplementedError as exc:
            raise HolidayCountryNotSupportedError(
                settings.holiday_country, settings.holiday_subdivision
            ) from exc

        added = 0
        for day, name in sorted(year_holidays.items()):
            if await self._non_working_days.get_by_day(day) is not None:
                continue
            await self._non_working_days.save(
                NonWorkingDay(day=day, name=name, kind=NonWorkingDayKind.PUBLIC_HOLIDAY)
            )
            added += 1
        return added
