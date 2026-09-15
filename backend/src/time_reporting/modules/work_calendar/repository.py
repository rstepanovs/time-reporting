"""Persistence of ``NonWorkingDay`` entities. Flushes but never commits — the bus owns
transactions."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import extract, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.work_calendar.contracts import NonWorkingDayAlreadyExistsError
from time_reporting.modules.work_calendar.models import NonWorkingDay

_DAY_UNIQUE_CONSTRAINT = "uq_non_working_days_day"


class NonWorkingDayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, non_working_day_id: UUID) -> NonWorkingDay | None:
        return await self._session.get(NonWorkingDay, non_working_day_id)

    async def get_by_day(self, day: date) -> NonWorkingDay | None:
        result = await self._session.scalars(select(NonWorkingDay).where(NonWorkingDay.day == day))
        return result.one_or_none()

    async def list_for_year(self, year: int | None) -> Sequence[NonWorkingDay]:
        statement = select(NonWorkingDay).order_by(NonWorkingDay.day)
        if year is not None:
            statement = statement.where(extract("year", NonWorkingDay.day) == year)
        result = await self._session.scalars(statement)
        return result.all()

    async def list_in_range(self, date_from: date, date_to: date) -> Sequence[NonWorkingDay]:
        result = await self._session.scalars(
            select(NonWorkingDay)
            .where(NonWorkingDay.day >= date_from, NonWorkingDay.day <= date_to)
            .order_by(NonWorkingDay.day)
        )
        return result.all()

    async def save(self, non_working_day: NonWorkingDay) -> None:
        """Add ``non_working_day`` to the session (if new) and flush pending changes."""
        self._session.add(non_working_day)
        day = non_working_day.day  # read before flush: a failed flush may expire ORM attributes
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # A concurrent request may have taken the date after the service's pre-check.
            if _DAY_UNIQUE_CONSTRAINT in str(exc.orig):
                raise NonWorkingDayAlreadyExistsError(day) from exc
            raise

    async def delete(self, non_working_day: NonWorkingDay) -> None:
        await self._session.delete(non_working_day)
        await self._session.flush()
